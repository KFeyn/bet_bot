import hashlib
import io
import logging
from collections import defaultdict
import typing as tp

from aiogram import types
import matplotlib
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt

from app.dbworker import PostgresConnection

matplotlib.use('Agg')

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
for handler in logger.handlers:
    handler.setFormatter(formatter)


def is_integer(s: str) -> bool:
    try:
        int(s)
        return True
    except ValueError:
        return False


def generate_id(value: str) -> int:
    md5_hash = hashlib.md5(value.encode()).hexdigest()
    first_16_chars = md5_hash[:16]
    integer_value = int(first_16_chars, 16)
    if integer_value >= 2 ** 63:
        integer_value -= 2 ** 64
    return integer_value


def get_color(row) -> tp.Tuple[str, str]:
    if row[1] is None or row[2] is None:
        return 'yellow', 'yellow'
    elif row[1] > row[2] or (row[1] == row[2] and row[4] == 1):
        return 'green', 'red'
    elif row[1] < row[2] or (row[1] == row[2] and row[4] == 2):
        return 'red', 'green'
    else:
        return 'yellow', 'yellow'


def make_plot_two_teams(table_data: tp.List[tp.List], name: str) -> types.BufferedInputFile:
    fig, ax = plt.subplots(figsize=(12, 6), dpi=200)
    ax.axis('off')

    table = ax.table(cellText=table_data, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 2)

    for i, row in enumerate(table_data[1:], start=1):
        color1, color2 = get_color(row)
        table[(i, 0)].set_facecolor(color1)
        table[(i, 3)].set_facecolor(color2)

    plt.title(name)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    plt.close(fig)

    return types.BufferedInputFile(buf.read(), 'file.png')


def make_plot_points(table_data: tp.List[tp.List], name: str) -> types.BufferedInputFile:
    fig, ax = plt.subplots(figsize=(10, 6), dpi=200)
    ax.axis('off')

    new_table = [el[:3] for el in table_data]

    table = ax.table(cellText=new_table, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1.2, 1.5)

    for i, row in enumerate(table_data[1:], start=1):
        if row[2] < 0:
            color = 'red'
        elif row[2] == 0:
            color = 'yellow'
        else:
            color = 'green'
        table[(i, 0)].set_facecolor(color)
        table[(i, 1)].set_facecolor(color)
        table[(i, 2)].set_facecolor(color)

    plt.title(name)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    plt.close(fig)

    return types.BufferedInputFile(buf.read(), 'file.png')


def pivot_table(data: tp.List[tp.List]) -> tp.List[tp.List]:
    # Step 1: Initialize defaultdicts for storing points
    pair_points = defaultdict(lambda: defaultdict(int))

    # Step 2: Populate the defaultdicts with points
    for row in data[1:]:
        user_name, pair, points = row
        pair_points[pair][user_name] += points

    # Step 3: Determine all unique pairs and sort them
    pairs = sorted(set(row[1] for row in data[1:]))

    # Step 4: Compute the overall points for each user
    user_points = defaultdict(int)
    for pair in pairs:
        for user_name in pair_points[pair]:
            user_points[user_name] += pair_points[pair][user_name]

    # Step 5: Sort users by overall points in descending order
    sorted_users = sorted(user_points.keys(), key=lambda user: user_points[user], reverse=True)

    # Step 6: Create the result list in the desired format
    result = [['pair'] + sorted_users]

    # Add rows for each pair
    for pair in pairs:
        row = [pair]
        for user_name in sorted_users:
            row.append(pair_points[pair][user_name] if user_name in pair_points[pair] else None)
        result.append(row)

    # Add overall row
    overall_row = ['overall']
    for user_name in sorted_users:
        overall_row.append(user_points[user_name])
    result = result[:16]
    result.append(overall_row)

    return result


def make_plot_points_detailed(table_data: tp.List[tp.List], name: str) -> types.BufferedInputFile:
    def check_none(value: tp.Optional[float]) -> float:
        if value is None:
            return 0
        else:
            return float(value)

    table_data = pivot_table(table_data)

    all_values = [check_none(cell) for row in table_data[1:-1] for cell in row[1:]]
    vmin, vmax = min(all_values), max(all_values)

    cmap = matplotlib.colormaps['RdYlGn']
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    fig, ax = plt.subplots(figsize=(30, 10), dpi=200)
    ax.axis('off')

    table = ax.table(cellText=table_data, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 2)

    for i, row in enumerate(table_data[1:-1], start=1):
        for j, cell in enumerate(row[1:], start=1):
            color = cmap(norm(check_none(cell)))
            table[(i, j)].set_facecolor(color)

    plt.title(name)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    plt.close(fig)
    return types.BufferedInputFile(buf.read(), 'file.png')


async def generate_stage_keyboard(competition_id: int, pg_con: PostgresConnection) -> types.InlineKeyboardMarkup:
    query = f"""
    select
            stage
    from
            bets.matches
    where
            competition_id = {competition_id}
    group by 
            stage
    order by 
            min(dt)
    """
    stages = await pg_con.get_data(query)
    keyboard_buttons = []
    for stage in stages:
        stage = stage['stage']
        keyboard_buttons.append([types.InlineKeyboardButton(text=stage, callback_data=f'stage_{stage}')])

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return keyboard


def generate_stats_keyboard() -> types.InlineKeyboardMarkup:
    keyboard_buttons = [[types.InlineKeyboardButton(text='simple', callback_data='stats_simple')],
                        [types.InlineKeyboardButton(text='detailed', callback_data='stats_detailed')]]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return keyboard


def generate_competition_keyboard() -> types.InlineKeyboardMarkup:
    keyboard_buttons = [[types.InlineKeyboardButton(text='Champions League', callback_data='comps_CL')],
                        [types.InlineKeyboardButton(text='World Championship', callback_data='comps_WC')],
                        [types.InlineKeyboardButton(text='Europe Championship', callback_data='comps_Euro')]]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return keyboard


def generate_number_keyboard() -> types.InlineKeyboardMarkup:
    keyboard_buttons = []
    for i in range(11):
        keyboard_buttons.append([types.InlineKeyboardButton(text=str(i), callback_data=f'goals_{i}')])
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return keyboard


def generate_teams_keyboard(first_team_name: str, second_team_name: str) -> types.InlineKeyboardMarkup:
    keyboard_buttons = [[types.InlineKeyboardButton(text=first_team_name, callback_data='penalty_1')],
                        [types.InlineKeyboardButton(text=second_team_name, callback_data='penalty_2')]]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return keyboard


def generate_manage_groups_keyboard() -> types.InlineKeyboardMarkup:
    keyboard_buttons = [[types.InlineKeyboardButton(text="Create Group", callback_data="manage_creategroup")],
                        [types.InlineKeyboardButton(text="Delete Group", callback_data="manage_deletegroup")],
                        [types.InlineKeyboardButton(text="Delete User from Group",
                                                    callback_data="manage_deleteuserfromgroup")]]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return keyboard

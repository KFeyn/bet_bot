from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from ..dbworker import PostgresConnection
from ..utilities import logger


class OrderPlaceBets(StatesGroup):
    waiting_for_comp_and_group_picking = State()
    waiting_for_match_picking = State()
    waiting_for_first_team_goals = State()
    waiting_for_second_team_goals = State()
    waiting_for_penalty_winner = State()


def generate_number_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    for i in range(11):
        keyboard.add(types.InlineKeyboardButton(text=str(i), callback_data=f'goals_{i}'))
    return keyboard


def generate_teams_keyboard(first_team_name: str, second_team_name: str):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text=first_team_name, callback_data='penalty_1'))
    keyboard.add(types.InlineKeyboardButton(text=second_team_name, callback_data='penalty_2'))
    return keyboard


async def start_bet_process(message: types.Message, state: FSMContext, pg_con: PostgresConnection, new_bet=True):
    await state.finish()

    query_get = f"""
    select 
            comp.name || ' - ' || grp.name  as c_g_pair
            ,comp.id as competition_id
            ,grp.id as group_id
    from 
            bets.users_in_groups as uig
    join 
            bets.groups as grp
                on grp.id = uig.group_id
    join 
            bets.groups_in_competitions as gic
                    on uig.group_id = gic.group_id
    join
            bets.competitions as comp
                    on comp.id = gic.competition_id
                    and comp.end_date - now() > interval '1 hours'
    where 
            uig.user_id = {message.from_user.id}
    """
    comps = await pg_con.get_data(query_get)

    if len(comps) == 0:
        await message.answer("You don't participate in any competition!")
        return

    elif len(comps) > 1:
        keyboard = types.InlineKeyboardMarkup()
        for comp in comps:
            keyboard.add(types.InlineKeyboardButton(text=comp['c_g_pair'],
                                                    callback_data=f"competition_{comp['competition_id']}_"
                                                                  f"{comp['group_id']}"))
        msg = await message.answer("Please choose a competition and group pair:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id)
        await OrderPlaceBets.waiting_for_comp_and_group_picking.set()
    else:
        await state.update_data(competition_id=comps[0]['competition_id'], group_id=comps[0]['group_id'])
        await start_picking_match(message, state, pg_con, new_bet=new_bet)


async def start_placing_a_bet(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    await start_bet_process(message, state, pg_con, new_bet=True)


async def start_changing_a_bet(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    await start_bet_process(message, state, pg_con, new_bet=False)


async def competition_picked(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    competition_id, group_id = call.data.split('_')[1], call.data.split('_')[2]
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(competition_id=competition_id, group_id=group_id)
    await start_picking_match(call.message, state, pg_con)


async def start_picking_match(message: types.Message, state: FSMContext, pg_con: PostgresConnection, new_bet=True):
    user_data = await state.get_data()
    if new_bet:
        query_get = f"""
        select 
                first_team || ' - ' || second_team as pair
                ,id
                ,{message.from_user.id} as user_id
                ,dt::timestamp - interval '3 hours' as dt_in_utc_0
                ,'' as existing_bet
        from 
                bets.matches 
        where
                not exists (select 1 from bets.bets where bets.matches.id = bets.bets.match_id
                and bets.bets.user_id = {message.from_user.id})
                and competition_id = {user_data['competition_id']}
                and dt - now() > interval '1 hours'
        order by dt
        """
    else:
        query_get = f"""
        with pre_final as 
        (
        select 
                mtchs.first_team || ' - ' || mtchs.second_team as pair
                ,betting.match_id as id
                ,{message.from_user.id} as user_id
                ,mtchs.dt::timestamp - interval '3 hours' as dt_in_utc_0
                ,betting.first_team_goals || ':' || betting.second_team_goals || 
                    case 
                        when betting.penalty_winner = 0 then '' 
                        else ', ' || betting.penalty_winner || ' team wins penalty'
                    end
                as existing_bet
                ,row_number() over (partition by betting.match_id order by betting.insert_date desc) as rn
        from 
                bets.bets as betting
        join 
                bets.matches as mtchs
                    on betting.match_id = mtchs.id
        where
                betting.user_id = {message.from_user.id}
                and mtchs.dt - now() > interval '1 hours'
                and betting.competition_id = {user_data['competition_id']}
                and betting.group_id = {user_data['group_id']}
        )
        select 
                pair
                ,id
                ,user_id
                ,dt_in_utc_0
                ,existing_bet
        from
                pre_final
        where 
                rn = 1
        order by dt_in_utc_0
        """

    teams = await pg_con.get_data(query_get)

    if len(teams) == 0:
        await message.answer("You've placed all the bets!")
        return

    keyboard = types.InlineKeyboardMarkup()
    text_for_message = "Please choose a match:\n"
    for team in teams:
        callback_data = f"match_{team['id']}_{team['pair']}_{team['user_id']}"
        keyboard.add(types.InlineKeyboardButton(text=team['pair'], callback_data=callback_data))
        existing_part = '' if new_bet else f' ({team['existing_bet']})'
        text_for_message += f"{team['pair']}{existing_part}: {team['dt_in_utc_0']} UTC+0\n"
    msg = await message.answer(text_for_message, reply_markup=keyboard)
    await state.update_data(previous_message_id=msg.message_id)
    await OrderPlaceBets.waiting_for_match_picking.set()


async def match_picked(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    match_id, pair, user_id = call.data.split('_')[1], call.data.split('_')[2], call.data.split('_')[3]
    await state.update_data(match_id=match_id, pair=pair, user_id=user_id)
    first_team_name = pair.split('-')[0].strip()
    msg = await call.message.answer(f"Please enter the goals for the {first_team_name}:",
                                    reply_markup=generate_number_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await OrderPlaceBets.waiting_for_first_team_goals.set()


async def first_team_goals_entered(call: types.CallbackQuery, state: FSMContext):
    first_team_goals = int(call.data.split('_')[1])
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(first_team_goals=first_team_goals)
    second_team_name = user_data['pair'].split('-')[1].strip()
    msg = await call.message.answer(f"Please enter the goals for the {second_team_name}:",
                                    reply_markup=generate_number_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await OrderPlaceBets.waiting_for_second_team_goals.set()


async def second_team_goals_entered(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    second_team_goals = int(call.data.split('_')[1])
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(second_team_goals=second_team_goals)
    first_team_name, second_team_name = user_data['pair'].split(' - ')

    if user_data['first_team_goals'] == second_team_goals:
        msg = await call.message.answer("The scores are equal. Please choose the penalty winner:",
                                        reply_markup=generate_teams_keyboard(first_team_name, second_team_name))
        await state.update_data(previous_message_id=msg.message_id)
        await OrderPlaceBets.waiting_for_penalty_winner.set()
    else:
        await state.update_data(penalty_winner=0)
        await save_bet(call, state, pg_con)


async def penalty_winner_entered(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    penalty_winner = int(call.data.split('_')[1])
    await state.update_data(penalty_winner=penalty_winner)
    await save_bet(call, state, pg_con)


async def save_bet(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await pg_con.insert_data('bets.bets',
                             ['match_id', 'user_id', 'first_team_goals', 'second_team_goals',
                              'penalty_winner', 'group_id', 'competition_id'],
                             [(user_data['match_id'], user_data['user_id'], user_data['first_team_goals'],
                               user_data['second_team_goals'], user_data['penalty_winner'],
                               user_data['group_id'], user_data['competition_id'])])

    await call.message.answer("Your bet has been placed successfully!", reply_markup=types.ReplyKeyboardRemove())
    logger.info(f'Bet for match {user_data["match_id"]} for user {user_data["user_id"]} is written successfully')
    await state.finish()


def register_handlers_add_bet(dp: Dispatcher, pg_con: PostgresConnection):
    async def start_placing_a_bet_wrapper(message: types.Message, state: FSMContext):
        await start_placing_a_bet(message, state, pg_con)

    async def penalty_winner_entered_wrapper(call: types.CallbackQuery, state: FSMContext):
        await penalty_winner_entered(call, state, pg_con)

    async def second_team_goals_entered_wrapper(call: types.CallbackQuery, state: FSMContext):
        await second_team_goals_entered(call, state, pg_con)

    async def competition_picked_wrapper(call: types.CallbackQuery, state: FSMContext):
        await competition_picked(call, state, pg_con)

    async def start_changing_a_bet_wrapper(message: types.Message, state: FSMContext):
        await start_changing_a_bet(message, state, pg_con)

    dp.register_message_handler(start_placing_a_bet_wrapper, commands="add_bet", state="*")
    dp.register_message_handler(start_changing_a_bet_wrapper, commands="change_bet", state="*")
    dp.register_callback_query_handler(competition_picked_wrapper, lambda call: call.data.startswith('competition_'),
                                       state=OrderPlaceBets.waiting_for_comp_and_group_picking)
    dp.register_callback_query_handler(match_picked, lambda call: call.data.startswith('match_') or
                                       call.data.startswith('change_'),
                                       state=OrderPlaceBets.waiting_for_match_picking)
    dp.register_callback_query_handler(first_team_goals_entered, lambda call: call.data.startswith('goals_'),
                                       state=OrderPlaceBets.waiting_for_first_team_goals)
    dp.register_callback_query_handler(second_team_goals_entered_wrapper, lambda call: call.data.startswith('goals_'),
                                       state=OrderPlaceBets.waiting_for_second_team_goals)
    dp.register_callback_query_handler(penalty_winner_entered_wrapper, lambda call: call.data.startswith('penalty_'),
                                       state=OrderPlaceBets.waiting_for_penalty_winner)

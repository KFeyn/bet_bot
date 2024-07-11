from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter

from app.dbworker import PostgresConnection
from app.utils import make_plot_two_teams, generate_stage_keyboard, logger


class OrderCheckCompetitions(StatesGroup):
    waiting_for_competition_picking = State()
    waiting_for_stage_picking = State()


async def start_picking_competition(message: Message, state: FSMContext, pg_con: PostgresConnection):
    await state.clear()

    query_get = f"""
    select distinct
            cmp.name
            ,cmp.id 
    from 
            bets.competitions as cmp
    join
            bets.groups_in_competitions as gic
                on gic.competition_id = cmp.id
    join
            bets.users_in_groups as uig
                on uig.group_id = gic.group_id
    where 
            now() - end_date < interval '168 hours'
            and uig.user_id = {message.chat.id}
    """
    comps = await pg_con.get_data(query_get)

    if len(comps) == 0:
        await message.answer("There are no actual competitions!")
        return

    else:
        keyboard_buttons = []
        for comp in comps:
            keyboard_buttons.append([InlineKeyboardButton(text=comp['name'],
                                                          callback_data=f"competition_{comp['id']}_{comp['name']}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        msg = await message.answer("Please choose a competition:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id, asking_user_id=str(message.chat.id))
        await state.set_state(OrderCheckCompetitions.waiting_for_competition_picking)


async def competition_picked(call: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    competition_id, competition_name = call.data.split('_')[1], call.data.split('_')[2]
    await state.update_data(competition_id=competition_id, competition_name=competition_name)

    msg = await call.message.answer("Please enter the stage:", reply_markup=generate_stage_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await state.set_state(OrderCheckCompetitions.waiting_for_stage_picking)


async def send_image(call: CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    stage = call.data.split('_')[1]
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    query_get = f"""
    select 
            first_team
            ,first_team_goals
            ,second_team_goals
            ,second_team
            ,penalty_winner 
            ,dt::timestamp - interval '3 hours' as dt_in_utc_0
    from 
            bets.matches
    where 
            stage = '{stage}'
            and competition_id = {user_data['competition_id']}
    order by 6
    """

    matches = await pg_con.get_data(query_get)

    if len(matches) == 0:
        await call.message.answer('There are no matches on this stage!')
        return

    keys = list(matches[0].keys())
    values = [list(match.values()) for match in matches]
    image = make_plot_two_teams([keys] + values, f"Matches of {user_data['competition_name']} for {stage}")

    await call.message.bot.send_photo(call.message.chat.id, image, caption="Here are results")
    logger.info(f"Image of competition for {user_data['asking_user_id']} sent successfully")


def register_handlers_check_competition(router: Router, pg_con: PostgresConnection):
    async def start_picking_competition_wrapper(message: Message, state: FSMContext):
        await start_picking_competition(message, state, pg_con)

    async def send_image_wrapper(call: CallbackQuery, state: FSMContext):
        await send_image(call, state, pg_con)

    router.message.register(start_picking_competition_wrapper, Command(commands=["check_competition"]))
    router.callback_query.register(competition_picked, F.data.startswith('competition_'),
                                   StateFilter(OrderCheckCompetitions.waiting_for_competition_picking))
    router.callback_query.register(send_image_wrapper, F.data.startswith('stage_'),
                                   StateFilter(OrderCheckCompetitions.waiting_for_stage_picking))

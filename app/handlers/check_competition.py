from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from ..dbworker import PostgresConnection
from ..utilities import make_plot_two_teams, generate_stage_keyboard, logger


class OrderCheckCompetitions(StatesGroup):
    waiting_for_competition_picking = State()
    waiting_for_stage_picking = State()


async def start_picking_competition(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    await state.finish()

    query_get = f"""
    select 
            name
            ,id 
    from 
            bets.competitions
    where 
            now() - end_date < interval '168 hours'
    """
    comps = await pg_con.get_data(query_get)

    if len(comps) == 0:
        await message.answer("There are no actual competitions!")
        return

    else:
        keyboard = types.InlineKeyboardMarkup()
        for comp in comps:
            keyboard.add(types.InlineKeyboardButton(text=comp['name'],
                                                    callback_data=f"competition_{comp['id']}_{comp['name']}"))
        msg = await message.answer("Please choose a competition:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id, asking_username=str(message.from_user.username))
        await OrderCheckCompetitions.waiting_for_competition_picking.set()


async def competition_picked(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    competition_id, competition_name = call.data.split('_')[1], call.data.split('_')[2]
    await state.update_data(competition_id=competition_id, competition_name=competition_name)

    msg = await call.message.answer("Please enter the stage:", reply_markup=generate_stage_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await OrderCheckCompetitions.waiting_for_stage_picking.set()


async def send_image(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
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
    logger.info(f"Image of bets for {user_data['asking_username']} sent successfully")


def register_handlers_check_competition(dp: Dispatcher, pg_con: PostgresConnection):
    async def start_picking_competition_wrapper(message: types.Message, state: FSMContext):
        await start_picking_competition(message, state, pg_con)

    async def send_image_wrapper(call: types.CallbackQuery, state: FSMContext):
        await send_image(call, state, pg_con)

    dp.register_message_handler(start_picking_competition_wrapper, commands="check_competition", state="*")
    dp.register_callback_query_handler(competition_picked, lambda call: call.data.startswith('competition_'),
                                       state=OrderCheckCompetitions.waiting_for_competition_picking)
    dp.register_callback_query_handler(send_image_wrapper, lambda call: call.data.startswith('stage_'),
                                       state=OrderCheckCompetitions.waiting_for_stage_picking)

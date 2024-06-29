from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from ..dbworker import PostgresConnection
from ..utilities import make_plot_two_teams, generate_stage_keyboard, logger


class OrderCheckBets(StatesGroup):
    waiting_for_comp_and_group_picking = State()
    waiting_for_stage_picking = State()
    waiting_for_match_picking = State()


async def start_check_process(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
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
                    and now() - comp.end_date < interval '168 hours'
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
        await state.update_data(previous_message_id=msg.message_id, asking_user_id=str(message.from_user.id))
        await OrderCheckBets.waiting_for_comp_and_group_picking.set()
    else:
        await state.update_data(competition_id=comps[0]['competition_id'], group_id=comps[0]['group_id'],
                                asking_user_id=str(message.from_user.id))

        msg = await message.answer("Please enter the stage:", reply_markup=generate_stage_keyboard())
        await state.update_data(previous_message_id=msg.message_id)
        await OrderCheckBets.waiting_for_stage_picking.set()


async def competition_picked(call: types.CallbackQuery, state: FSMContext):
    competition_id, group_id = call.data.split('_')[1], call.data.split('_')[2]
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(competition_id=competition_id, group_id=group_id)

    msg = await call.message.answer("Please enter the stage:", reply_markup=generate_stage_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await OrderCheckBets.waiting_for_stage_picking.set()


async def start_picking_match(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    stage = call.data.split('_')[1]
    await state.update_data(stage=stage)
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    query_get = f"""
    select 
                first_team || ' - ' || second_team as pair
                ,id
        from 
                bets.matches 
        where
                competition_id = {user_data['competition_id']}
                and stage = '{stage}'
                and dt < now()
        order by dt
    """

    matches = await pg_con.get_data(query_get)

    if len(matches) == 0:
        await call.message.answer("There are no bets on this stage or match didn\'t started yet")
        return

    keyboard = types.InlineKeyboardMarkup()
    for match in matches:
        keyboard.add(types.InlineKeyboardButton(text=match['pair'], callback_data=f"match_{match['id']}_"
                                                                                  f"{match['pair']}"))
    msg = await call.message.answer("Please choose a match:", reply_markup=keyboard)
    await state.update_data(previous_message_id=msg.message_id)
    await OrderCheckBets.waiting_for_match_picking.set()


async def match_picked(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    match_id, pair = call.data.split('_')[1], call.data.split('_')[2]
    await state.update_data(match_id=match_id, pair=pair)
    await send_image(call, state, pg_con)


async def send_image(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    match_id = call.data.split('_')[1]
    user_data = await state.get_data()

    query_get = f"""
    with cte as (
        select 
                mtchs.first_team
                ,mtchs.second_team
                ,betting.first_team_goals
                ,betting.second_team_goals
                ,betting.penalty_winner
                ,case when usr.id = {user_data['asking_user_id']} then 'Me' else usr.first_name || ' ' || usr.last_name 
                 end as name
                ,row_number() over (partition by betting.user_id order by betting.insert_date desc) as rn
                
        from 
                bets.bets as betting
        join 
                bets.matches as mtchs
                    on betting.match_id = mtchs.id
        join 
                bets.users as usr 
                    on usr.id = betting.user_id
        where 
                betting.competition_id = {user_data['competition_id']}
                and betting.group_id = {user_data['group_id']}
                and mtchs.stage = '{user_data['stage']}'
                and mtchs.id = '{match_id}'
        )
        select
                first_team
                ,first_team_goals
                ,second_team_goals
                ,second_team
                ,penalty_winner
                ,name
        from 
                cte
        where 
                rn = 1
        order by 6
    """

    bets = await pg_con.get_data(query_get)

    if len(bets) == 0:
        await call.message.answer('There are no bets on this stage or match didn\'t started yet')
        return

    keys = list(bets[0].keys())
    values = [list(bet.values()) for bet in bets]
    image = make_plot_two_teams([keys] + values, f"Bets for match {user_data['pair']}")

    await call.message.bot.send_photo(call.message.chat.id, image, caption="Here are results")
    logger.info(f"Image of bets for {user_data['asking_user_id']} sent successfully")


def register_handlers_check_bet(dp: Dispatcher, pg_con: PostgresConnection):
    async def start_check_process_wrapper(message: types.Message, state: FSMContext):
        await start_check_process(message, state, pg_con)

    async def competition_picked_wrapper(call: types.CallbackQuery, state: FSMContext):
        await competition_picked(call, state)

    async def start_picking_match_wrapper(call: types.CallbackQuery, state: FSMContext):
        await start_picking_match(call, state, pg_con)

    async def match_picked_wrapper(call: types.CallbackQuery, state: FSMContext):
        await match_picked(call, state, pg_con)

    dp.register_message_handler(start_check_process_wrapper, commands="check_others_bets", state="*")
    dp.register_callback_query_handler(competition_picked_wrapper, lambda call: call.data.startswith('competition_'),
                                       state=OrderCheckBets.waiting_for_comp_and_group_picking)
    dp.register_callback_query_handler(start_picking_match_wrapper, lambda call: call.data.startswith('stage_'),
                                       state=OrderCheckBets.waiting_for_stage_picking)
    dp.register_callback_query_handler(match_picked_wrapper, lambda call: call.data.startswith('match_'),
                                       state=OrderCheckBets.waiting_for_match_picking)

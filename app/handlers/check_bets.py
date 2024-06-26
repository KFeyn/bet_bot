import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from ..dbworker import PostgresConnection
from ..utilities import make_plot


class OrderCheckBets(StatesGroup):
    waiting_for_comp_and_group_picking = State()
    waiting_for_user_picking = State()
    waiting_for_stage_picking = State()


def generate_stage_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text='group stage', callback_data='stage_group stage'))
    keyboard.add(types.InlineKeyboardButton(text='1/8 final', callback_data='stage_1/8 final'))
    keyboard.add(types.InlineKeyboardButton(text='1/4 final', callback_data='stage_1/4 final'))
    keyboard.add(types.InlineKeyboardButton(text='1/2 final', callback_data='stage_1/2 final'))
    keyboard.add(types.InlineKeyboardButton(text='final', callback_data='stage_final'))
    return keyboard


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
                    and comp.end_date - now() > interval '24 hours'
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
        await OrderCheckBets.waiting_for_comp_and_group_picking.set()
    else:
        await state.update_data(competition_id=comps[0]['competition_id'], group_id=comps[0]['group_id'])
        await start_picking_user(message, state, pg_con)


async def competition_picked(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    competition_id, group_id = call.data.split('_')[1], call.data.split('_')[2]
    await state.update_data(competition_id=competition_id, group_id=group_id)
    await start_picking_user(call.message, state, pg_con)


async def start_picking_user(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    query_get = f"""
    select 
            users.id
            ,case when id = {message.from_user.id} then 'Me' else users.nickname end as nickname
    from 
            bets.users as users
    where 
            exists( select 1 from bets.bets as betting where
            betting.competition_id = {user_data['competition_id']}
            and betting.group_id = {user_data['group_id']}
            and betting.user_id = users.id)
    """

    users = await pg_con.get_data(query_get)

    if len(users) == 0:
        await message.answer("There is no bets from this user!")
        return

    keyboard = types.InlineKeyboardMarkup()
    for user in users:
        keyboard.add(types.InlineKeyboardButton(text=user['nickname'], callback_data=f"user__{user['id']}__"
                                                                                     f"{user['nickname']}"))
    msg = await message.answer("Please choose a user:", reply_markup=keyboard)
    await state.update_data(previous_message_id=msg.message_id)
    await OrderCheckBets.waiting_for_user_picking.set()


async def user_picked(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    user_id, user_nickname = call.data.split('__')[1], call.data.split('__')[2]
    await state.update_data(user_id=user_id, user_nickname=user_nickname)

    msg = await call.message.answer("Please enter the goals for the first team:",
                                    reply_markup=generate_stage_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await OrderCheckBets.waiting_for_stage_picking.set()


async def send_image(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    stage = call.data.split('_')[1]
    user_data = await state.get_data()
    query_get = f"""
    with cte as (
        select 
                mtchs.first_team
                ,mtchs.second_team
                ,betting.first_team_goals
                ,betting.second_team_goals
                ,betting.is_penalty
                ,betting.penalty_winner
                ,row_number() over (partition by betting.match_id order by betting.insert_date desc) as rn
                
        from 
                bets.bets as betting
        join 
                bets.matches as mtchs
                    on betting.match_id = mtchs.id
        where 
                betting.competition_id = {user_data['competition_id']}
                and betting.group_id = {user_data['group_id']}
                and betting.user_id = {user_data['user_id']}
                and mtchs.stage = '{stage}'
        )
        select
                first_team
                ,first_team_goals
                ,second_team_goals
                ,second_team
                ,is_penalty
                ,penalty_winner
        from 
                cte
        where 
                rn = 1
    """

    bets = await pg_con.get_data(query_get)

    if len(bets) == 0:
        await call.message.answer('There are no bets from this user on this stage!')
        return

    keys = list(bets[0].keys())
    values = [list(bet.values()) for bet in bets]
    image = await make_plot([keys] + values, f"Bets of {user_data['user_nickname']} for {stage}")

    await call.message.bot.send_photo(call.message.chat.id, image, caption="Here are results")
    logging.info(f"Image of bets for {user_data['user_nickname']} sent successfully")


def register_handlers_check_bet(dp: Dispatcher, pg_con: PostgresConnection):
    async def start_check_process_wrapper(message: types.Message, state: FSMContext):
        await start_check_process(message, state, pg_con)

    async def competition_picked_wrapper(call: types.CallbackQuery, state: FSMContext):
        await competition_picked(call, state, pg_con)

    async def user_picked_wrapper(call: types.CallbackQuery, state: FSMContext):
        await user_picked(call, state)

    async def send_image_wrapper(call: types.CallbackQuery, state: FSMContext):
        await send_image(call, state, pg_con)

    dp.register_message_handler(start_check_process_wrapper, commands="check_others_bets", state="*")
    dp.register_callback_query_handler(competition_picked_wrapper, lambda call: call.data.startswith('competition_'),
                                       state=OrderCheckBets.waiting_for_comp_and_group_picking)
    dp.register_callback_query_handler(user_picked_wrapper, lambda call: call.data.startswith('user__'),
                                       state=OrderCheckBets.waiting_for_user_picking)
    dp.register_callback_query_handler(send_image_wrapper, lambda call: call.data.startswith('stage_'),
                                       state=OrderCheckBets.waiting_for_stage_picking)

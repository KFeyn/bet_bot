from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from ..dbworker import PostgresConnection
from ..utilities import make_plot_points, logger, generate_stats_keyboard, make_plot_points_detailed


class OrderCheckLeaders(StatesGroup):
    waiting_for_comp_and_group_picking = State()
    waiting_for_type_picking = State()


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
            uig.user_id = {message.chat.id}
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
        await state.update_data(previous_message_id=msg.message_id, asking_user_id=str(message.chat.id))
        await OrderCheckLeaders.waiting_for_comp_and_group_picking.set()
    else:
        await state.update_data(competition_id=comps[0]['competition_id'], group_id=comps[0]['group_id'],
                                asking_user_id=str(message.chat.id))

        msg = await message.answer("Please enter type of info:", reply_markup=generate_stats_keyboard())
        await state.update_data(previous_message_id=msg.message_id)
        await OrderCheckLeaders.waiting_for_type_picking.set()


async def competition_picked(call: types.CallbackQuery, state: FSMContext):
    competition_id, group_id = call.data.split('_')[1], call.data.split('_')[2]
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(competition_id=competition_id, group_id=group_id)

    msg = await call.message.answer("Please enter type of info:", reply_markup=generate_stats_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await OrderCheckLeaders.waiting_for_type_picking.set()


async def type_picked(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    statistics_type = call.data.split('_')[1]
    await state.update_data(statistics_type=statistics_type)
    await send_image(call.message, state, pg_con)


async def send_image(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()

    stat_type = user_data['statistics_type']
    if stat_type == 'simple':
        query_get = f"""
        select
                user_name 
                ,points
                ,money_
        from 
                bets.points
        where 
                competition_id = {user_data['competition_id']}
                and group_id = {user_data['group_id']}
        order by 
                points desc
        """
    else:
        query_get = f"""
        select
                user_name
                ,stage || ': ' || pair as pair 
                ,points
        from 
                bets.points_detailed
        where 
                competition_id = {user_data['competition_id']}
                and group_id = {user_data['group_id']}
        """

    points = await pg_con.get_data(query_get)

    if len(points) == 0:
        await message.answer('There are no users with bets in this competition!')
        return

    keys = list(points[0].keys())
    values = [list(bet.values()) for bet in points]

    if stat_type == 'simple':
        image = make_plot_points([keys] + values, f"Points table")
    else:
        image = make_plot_points_detailed([keys] + values, f"Points table")

    await message.bot.send_photo(message.chat.id, image, caption="Here are results")
    logger.info(f"Image of points for {user_data['asking_user_id']} sent successfully")


def register_handlers_check_leaders(dp: Dispatcher, pg_con: PostgresConnection):
    async def start_check_process_wrapper(message: types.Message, state: FSMContext):
        await start_check_process(message, state, pg_con)

    async def type_picked_wrapper(call: types.CallbackQuery, state: FSMContext):
        await type_picked(call, state, pg_con)

    dp.register_message_handler(start_check_process_wrapper, commands="check_leaders", state="*")
    dp.register_callback_query_handler(competition_picked, lambda call: call.data.startswith('competition_'),
                                       state=OrderCheckLeaders.waiting_for_comp_and_group_picking)
    dp.register_callback_query_handler(type_picked_wrapper, lambda call: call.data.startswith('stats_'),
                                       state=OrderCheckLeaders.waiting_for_type_picking)

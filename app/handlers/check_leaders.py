from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter

from app.dbworker import PostgresConnection
from app.utils import make_plot_points, logger, generate_stats_keyboard, make_plot_points_detailed


class OrderCheckLeaders(StatesGroup):
    waiting_for_comp_and_group_picking = State()
    waiting_for_type_picking = State()


async def start_check_process(message: Message, state: FSMContext, pg_con: PostgresConnection):
    await state.clear()

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
        keyboard_buttons = []
        for comp in comps:
            keyboard_buttons.append([InlineKeyboardButton(text=comp['c_g_pair'],
                                                          callback_data=f"competition_{comp['competition_id']}_"
                                                                        f"{comp['group_id']}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        msg = await message.answer("Please choose a competition and group pair:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id, asking_user_id=str(message.chat.id))
        await state.set_state(OrderCheckLeaders.waiting_for_comp_and_group_picking)
    else:
        await state.update_data(competition_id=comps[0]['competition_id'], group_id=comps[0]['group_id'],
                                asking_user_id=str(message.chat.id))

        msg = await message.answer("Please enter type of info:", reply_markup=generate_stats_keyboard())
        await state.update_data(previous_message_id=msg.message_id)
        await state.set_state(OrderCheckLeaders.waiting_for_type_picking)


async def competition_picked(call: CallbackQuery, state: FSMContext):
    competition_id, group_id = call.data.split('_')[1], call.data.split('_')[2]
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(competition_id=competition_id, group_id=group_id)

    msg = await call.message.answer("Please enter type of info:", reply_markup=generate_stats_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await state.set_state(OrderCheckLeaders.waiting_for_type_picking)


async def type_picked(call: CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    statistics_type = call.data.split('_')[1]
    await state.update_data(statistics_type=statistics_type)
    await send_image(call.message, state, pg_con)


async def send_image(message: Message, state: FSMContext, pg_con: PostgresConnection):
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


def register_handlers_check_leaders(router: Router, pg_con: PostgresConnection):
    async def start_check_process_wrapper(message: Message, state: FSMContext):
        await start_check_process(message, state, pg_con)

    async def type_picked_wrapper(call: CallbackQuery, state: FSMContext):
        await type_picked(call, state, pg_con)

    router.message.register(start_check_process_wrapper, Command(commands=["check_leaders"]))
    router.callback_query.register(competition_picked, F.data.startswith('competition_'),
                                   StateFilter(OrderCheckLeaders.waiting_for_comp_and_group_picking))
    router.callback_query.register(type_picked_wrapper, F.data.startswith('stats_'),
                                   StateFilter(OrderCheckLeaders.waiting_for_type_picking))

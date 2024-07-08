from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext

from app.dbworker import PostgresConnection
from app.utilities import logger
from app.handlers.manage_groups.states import OrderDeleteUser, ManageGroupsMenu


async def start_deleting_user_from_group(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])

    query = f"""
    select
            grps.id
            ,grps.name
    from 
            bets.groups as grps
    join
            bets.users_in_groups as uig
                on uig.group_id = grps.id
    where
            uig.user_id = {call.message.chat.id}
            and uig.is_admin = True
    """
    grps = await pg_con.get_data(query)

    if len(grps) == 0:
        await call.message.answer("You are not an administrator in any group!")
        return

    elif len(grps) > 1:
        keyboard = types.InlineKeyboardMarkup()
        for grp in grps:
            keyboard.add(types.InlineKeyboardButton(text=grp['name'], callback_data=f"grp_{grp['id']}"))
        msg = await call.message.answer("Please choose group:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id, asking_user_id=str(call.message.chat.id))
        await OrderDeleteUser.waiting_for_group_picking.set()
    else:
        await state.update_data(group_id=grps[0]['id'], asking_user_id=str(call.message.chat.id))
        await pick_user_from_group(call.message, state, pg_con)


async def group_picked(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    group_id = call.data.split('_')[1]
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(group_id=group_id)
    await pick_user_from_group(call.message, state, pg_con)


async def pick_user_from_group(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    query = f"""
    select
            usr.id
            ,usr.first_name || ' ' || usr.last_name as user_name
    from 
            bets.groups as grps
    join
            bets.users_in_groups as uig
                on uig.group_id = grps.id
    join 
            bets.users as usr
                on usr.id = uig.user_id
    where
            uig.user_id != {user_data['asking_user_id']}
            and uig.group_id = {user_data['group_id']}
            and not exists (select 1 from bets.bets as bts where bts.user_id = usr.id and bts.group_id = grps.id)
    """
    users = await pg_con.get_data(query)

    if len(users) == 0:
        await message.answer("There are no members in this group or they placed bets!")
        return
    else:
        keyboard = types.InlineKeyboardMarkup()
        for usr in users:
            keyboard.add(types.InlineKeyboardButton(text=usr['user_name'], callback_data=f"usr_{usr['id']}"))
        msg = await message.answer("Please choose group member:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id)
        await OrderDeleteUser.waiting_for_group_picking.set()


async def delete_user_from_group(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    user_id = call.data.split('_')[1]
    await pg_con.delete_data('bets.users_in_groups', f"group_id = {user_data['group_id']} and user_id = {user_id}")
    await call.message.answer(f"You deleted user {user_id} successfully")
    logger.info(f"User {user_data['asking_user_id']} deleted user {user_id} from group {user_data['group_id']}")


def register_handlers_delete_users_from_groups(dp: Dispatcher, pg_con: PostgresConnection):

    async def start_deleting_user_from_group_wrapper(call: types.CallbackQuery, state: FSMContext):
        await start_deleting_user_from_group(call, state, pg_con)

    async def group_picked_wrapper(call: types.CallbackQuery, state: FSMContext):
        await group_picked(call, state, pg_con)

    async def delete_user_from_group_wrapper(call: types.CallbackQuery, state: FSMContext):
        await delete_user_from_group(call, state, pg_con)

    dp.register_callback_query_handler(start_deleting_user_from_group_wrapper,
                                       state=ManageGroupsMenu.waiting_for_action_choice)
    dp.register_callback_query_handler(group_picked_wrapper, lambda call: call.data.startswith('grp_'),
                                       state=OrderDeleteUser.waiting_for_group_picking)
    dp.register_callback_query_handler(delete_user_from_group_wrapper, lambda call: call.data.startswith('usr_'),
                                       state=OrderDeleteUser.waiting_for_user_picking)

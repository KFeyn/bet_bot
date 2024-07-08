from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext

from app.dbworker import PostgresConnection
from app.utilities import logger
from app.handlers.manage_groups.states import OrderDeleteGroup, ManageGroupsMenu


async def start_deleting_group(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):

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
            and uig.is_admin = true
            and not exists (select 1 from bets.bets as bts where bts.group_id = grps.id) 
    """
    grps = await pg_con.get_data(query)

    if len(grps) == 0:
        await call.message.answer("You are not an administrator in any group!")
        return

    else:
        keyboard = types.InlineKeyboardMarkup()
        for grp in grps:
            keyboard.add(types.InlineKeyboardButton(text=grp['name'], callback_data=f"grp_{grp['id']}"))
        msg = await call.message.answer("Please choose group:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id, asking_user_id=str(call.message.chat.id))
        await OrderDeleteGroup.waiting_for_group_picking.set()


async def delete_groups(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    group_id = call.data.split('_')[1]

    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])

    await pg_con.delete_data('bets.users_in_groups', f"group_id = {group_id}")
    await pg_con.delete_data('bets.groups_in_competitions', f"group_id = {group_id}")
    await pg_con.delete_data('bets.groups', f"id = {group_id}")
    await call.message.answer(f"You deleted group {group_id} successfully")
    logger.info(f"User {user_data['asking_user_id']} deleted group {group_id}")


def register_handlers_delete_groups(dp: Dispatcher, pg_con: PostgresConnection):

    async def start_deleting_group_wrapper(call: types.CallbackQuery, state: FSMContext):
        await start_deleting_group(call, state, pg_con)

    async def delete_groups_wrapper(call: types.CallbackQuery, state: FSMContext):
        await delete_groups(call, state, pg_con)

    dp.register_callback_query_handler(start_deleting_group_wrapper, state=ManageGroupsMenu.waiting_for_action_choice)
    dp.register_callback_query_handler(delete_groups_wrapper, lambda call: call.data.startswith('grp_'),
                                       state=OrderDeleteGroup.waiting_for_group_picking)

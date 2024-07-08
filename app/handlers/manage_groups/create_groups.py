from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.utils.deep_linking import get_start_link
import random
import asyncpg

from app.dbworker import PostgresConnection
from app.utilities import logger, generate_competition_keyboard, generate_id, is_integer
from app.model import Competition
from app.handlers.manage_groups.states import OrderCreateGroup, ManageGroupsMenu


async def check_groups(pg_con: PostgresConnection, user_id: int) -> bool:
    query = f"""
    select
            count(*) as cnt
    from 
            bets.groups_in_competitions
    where
            added_by = {user_id}
    """
    nums = await pg_con.get_data(query)

    if int(nums[0]['cnt']) <= 2:
        return True
    return False


async def choose_competition(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])

    msg = await call.message.answer("Please choose a competition:", reply_markup=generate_competition_keyboard())
    await state.update_data(previous_message_id=msg.message_id, asking_user_id=str(msg.chat.id))
    await OrderCreateGroup.waiting_for_comp_picking.set()


async def choose_money(call: types.CallbackQuery, state: FSMContext):
    competition_name = call.data.split('_')[1]

    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    msg = await call.message.answer("Type amount of money:")
    await state.update_data(previous_message_id=msg.message_id, competition_name=competition_name)
    await OrderCreateGroup.waiting_for_money_picking.set()


async def create_invite_link(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    money = message.text
    if is_integer(money):
        user_data = await state.get_data()
        await message.bot.delete_message(message.chat.id, user_data['previous_message_id'])
        competition_name = user_data['competition_name']
        user_id = user_data['asking_user_id']

        if not await check_groups(pg_con, user_id):
            await message.answer('You reached limit of three group!')
            return

        competition = Competition.from_message((competition_name,))
        await competition.check_existing(pg_con)

        group_name = f'{competition.name} group {random.randint(0, 10 ** 12)}'
        link = await get_start_link(group_name + '_' + str(user_id), encode=True)

        try:
            await pg_con.insert_data('bets.groups',
                                     ['name'],
                                     [(group_name,)])
            await pg_con.insert_data('bets.groups_in_competitions',
                                     ['group_id', 'competition_id', 'added_by', 'money', 'invite_link'],
                                     [(generate_id(group_name), competition.id, user_id, money, link)])
            await pg_con.insert_data('bets.users_in_groups',
                                     ['user_id', 'group_id', 'added_by', 'is_admin'],
                                     [(user_id, generate_id(group_name), user_id, True)])
        except asyncpg.exceptions.UniqueViolationError:
            await message.answer('We got a double, please retry')
            logger.error('We have got an UniqueViolationError when creating group')
            await state.finish()
            return
        except asyncpg.exceptions.PostgresError as e:
            await message.answer('We got a bug, please write to @sartrsmotritkrivo')
            logger.error(f'We have got an unexpected error {e} ')
            await state.finish()
            return

        await message.answer(f"Invite link created:\n```{link}```\nSend it to users you want to add to this group",
                             parse_mode=types.ParseMode.MARKDOWN)
        await state.finish()
        logger.info(f'User {user_id} created group {generate_id(group_name)} in competition {competition.id}')
    else:
        await message.reply('It is not a number, please type correct number')
        await OrderCreateGroup.waiting_for_money_picking.set()


def register_handlers_create_groups(dp: Dispatcher, pg_con: PostgresConnection):
    async def create_invite_link_wrapper(message: types.Message, state: FSMContext):
        await create_invite_link(message, state, pg_con)

    dp.register_callback_query_handler(choose_competition, state=ManageGroupsMenu.waiting_for_action_choice)
    dp.register_callback_query_handler(choose_money, lambda call: call.data.startswith('comps_'),
                                       state=OrderCreateGroup.waiting_for_comp_picking)
    dp.register_message_handler(create_invite_link_wrapper, state=OrderCreateGroup.waiting_for_money_picking)

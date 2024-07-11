import binascii

from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.deep_linking import decode_payload

from app.dbworker import PostgresConnection
from app.models import User, UserInGroup
from app.utils import generate_id, logger


class OrderStates(StatesGroup):
    waiting_for_start = State()
    waiting_for_help = State()


async def starting_message(message: types.Message, state: FSMContext, command: CommandObject,
                           pg_con: PostgresConnection):
    await state.clear()
    user = User.from_id((message.chat.id, message.chat.first_name, message.chat.last_name,
                         message.chat.username))
    await user.check_existing(pg_con)

    logger.info(f'User {message.chat.first_name} {message.chat.last_name} logged in')

    args = command.args
    if args:
        try:
            reference = decode_payload(args)
        except binascii.Error:
            await message.answer('Wrong link!')
            return

        try:
            added_by = int(reference.split('_')[1])
            group_name = reference.split('_')[0]
        except (IndexError, ValueError):
            await message.answer('Wrong link!')
            return

        uig = UserInGroup.from_message((message.chat.id, generate_id(group_name), added_by))

        if await uig.check_existing_group(pg_con):
            await uig.check_existing(pg_con)
        else:
            await message.answer('There is no such group, your link is deprecated!')
            return

    await message.answer("Hi! It's betting bot. Please check /help to check the rules", parse_mode="HTML")


async def helping_message(message: types.Message):
    await message.answer('Check rules here https://telegra.ph/Match-Prediction-Competition-Rules-06-27')


async def wrong_command_message(message: types.Message):
    logger.info(f'User {message.chat.first_name} {message.chat.last_name} wrote {message.text}')
    await message.answer("Wrong command")


def register_handlers_common(router: Router, pg_con: PostgresConnection):
    async def starting_message_wrapper(message: types.Message, command: CommandObject, state: FSMContext):
        await starting_message(message, state, command, pg_con)

    router.message.register(starting_message_wrapper, Command(commands=["start"]))
    router.message.register(helping_message, Command(commands=["help"]))
    router.message.register(wrong_command_message)

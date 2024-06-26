import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
import aiogram.utils.markdown as fmt
from aiogram.types.message import ContentType

from ..model import User
from ..dbworker import PostgresConnection


async def starting_message(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    """
    Fills users data if he doesn't exist

    :param message: message
    :param state: state
    :param pg_con: postgres connection
    """
    await state.finish()

    user = User.from_id((message.from_user.username,))
    await user.check_existing(pg_con)

    logging.info(f'User {message.from_user.first_name} {message.from_user.last_name} logged in')

    await message.answer("Hi! It's betting bot. Please check /help to know about existing commands",
                         parse_mode=types.ParseMode.HTML)


async def helping_message(message: types.Message):
    """
    List of coommands

    :param message: message
    """
    await message.answer(fmt.text("I know next commands:", "",
                                  "", sep='\n'))


async def wrong_command_message(message: types.Message):
    """
    Reacts on wrong commands

    :param message: message
    """

    logging.info(f'User {message.from_user.first_name} {message.from_user.last_name} wrote {message.text}')

    await message.answer("Wrong command. Check /help")


def register_handlers_common(dp: Dispatcher, pg_con: PostgresConnection):
    async def starting_message_wrapper(message: types.Message, state: FSMContext):
        await starting_message(message, state, pg_con)

    dp.register_message_handler(starting_message_wrapper, commands="start", state="*")
    dp.register_message_handler(helping_message, commands="help")
    dp.register_message_handler(wrong_command_message, content_types=ContentType.ANY)

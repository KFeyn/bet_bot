import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from app.dbworker import PostgresConnection
from app.handlers import (register_handlers_add_bet, register_handlers_check_bet,
                          register_handlers_check_competition, register_handlers_check_leaders,
                          register_handlers_common, register_handlers_manage_groups)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s+3h - %(levelname)s - %(name)s - %(message)s",
)


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command='/add_bet', description='Make a bet'),
        BotCommand(command='/change_bet', description='Change bet'),
        BotCommand(command='/check_others_bets', description='Check others bet'),
        BotCommand(command='/check_competition', description='Check competition results'),
        BotCommand(command='/check_leaders', description='Check points of users'),
        BotCommand(command='/manage_groups', description='Manage groups'),
        BotCommand(command='/help', description='Help')
    ]
    await bot.set_my_commands(commands)


async def main():
    bot = Bot(token=os.environ.get('BOT_TOKEN'))
    pg_connection = PostgresConnection(user=os.environ.get('PG_user'), password=os.environ.get('PG_password'),
                                       dbname=os.environ.get('PG_db'), host=os.environ.get('PG_host'))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    router = Router()
    register_handlers_add_bet(router, pg_connection)
    register_handlers_check_competition(router, pg_connection)
    register_handlers_check_leaders(router, pg_connection)
    register_handlers_check_bet(router, pg_connection)
    register_handlers_manage_groups(router, pg_connection)
    register_handlers_common(router, pg_connection)

    dp.include_routers(router)

    await set_commands(bot)

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

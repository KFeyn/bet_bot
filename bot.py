import asyncio
import logging
import os
from aiogram.types import BotCommand
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram import Bot, Dispatcher

from app.handlers.common import register_handlers_common
from app.handlers.placing_bets import register_handlers_add_bet
from app.handlers.check_bets import register_handlers_check_bet
from app.handlers.check_competition import register_handlers_check_competition
from app.handlers.check_leaders import register_handlers_check_leaders
from app.handlers.manage_groups.manage_groups import register_handlers_manage_groups
from app.dbworker import PostgresConnection

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
    dp = Dispatcher(bot, storage=MemoryStorage())

    register_handlers_add_bet(dp, pg_connection)
    register_handlers_check_bet(dp, pg_connection)
    register_handlers_check_competition(dp, pg_connection)
    register_handlers_check_leaders(dp, pg_connection)
    register_handlers_manage_groups(dp, pg_connection)
    register_handlers_common(dp, pg_connection)

    await set_commands(bot)

    await dp.skip_updates()
    await dp.start_polling()


if __name__ == '__main__':
    asyncio.run(main())

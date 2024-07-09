import asyncio
import os
from aiogram import Bot, Dispatcher, Router
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers.common import register_handlers_common
from app.handlers.placing_bets import register_handlers_add_bet
from app.handlers.check_bets import register_handlers_check_bet
from app.handlers.check_competition import register_handlers_check_competition
from app.handlers.check_leaders import register_handlers_check_leaders
from app.handlers.manage_groups.manage_groups import register_handlers_manage_groups
from app.dbworker import PostgresConnection


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

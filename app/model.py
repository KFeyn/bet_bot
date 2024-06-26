from __future__ import annotations
import dataclasses
from app.dbworker import PostgresConnection
import logging


@dataclasses.dataclass
class User:
    telegram_id: str

    @classmethod
    def from_id(cls, row: tuple) -> User:
        return cls(
            telegram_id=str(row[0])
        )

    async def check_existing(self, pg_con: PostgresConnection) -> None:
        query = f"""
        select 
                id
        from 
                bets.users
        where 
                telegram_id = '{self.telegram_id}'
        """
        if await pg_con.get_data(query):
            pass
        else:
            await pg_con.insert_data('bets.users', ['telegram_id'], [(self.telegram_id,)])
            logging.info(f'User {self.telegram_id} created')

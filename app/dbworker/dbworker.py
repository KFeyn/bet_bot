import typing as tp
import asyncpg
import logging


class PostgresConnection:
    def __init__(self, dbname: str, user: str, password: str, host: str):
        self.user = user
        self.password = password
        self.host = host
        self.dbname = dbname
        self.conn_string = f'postgresql://{self.user}:{self.password}@{self.host}:6432/{self.dbname}'

    async def get_data(self, query: str) -> tp.List:
        conn = await asyncpg.connect(self.conn_string)
        try:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def insert_data(self, table_name: str, columns: tp.List[str], data: tp.List[tp.Tuple]):
        """
        Inserts data into the specified table.

        :param table_name: The name of the table to insert data into.
        :param columns: A list of column names.
        :param data: A list of tuples, where each tuple represents a row of data.
        """
        conn = await asyncpg.connect(self.conn_string)
        try:
            async with conn.transaction():
                insert_stmt = f"""
                    INSERT INTO {table_name} ({', '.join(columns)}) VALUES 
                    {', '.join([str(row) if len(row) > 1 else str(row).replace(',', '') for row in data])}
                """
                await conn.execute(insert_stmt)
        except Exception as e:
            logging.error(f"Error inserting data: {e}")
            raise
        finally:
            await conn.close()

    async def delete_data(self, table_name: str, condition: str):
        """
        Deletes rows from the specified table based on a condition.

        :param table_name: The name of the table from which to delete data.
        :param condition: The condition to filter rows to be deleted (e.g., "id = 1").
        """
        conn = await asyncpg.connect(self.conn_string)
        try:
            async with conn.transaction():
                delete_stmt = f"""
                    DELETE FROM {table_name}
                    WHERE {condition}
                """
                await conn.execute(delete_stmt)
        except Exception as e:
            logging.error(f"Error deleting data: {e}")
            raise
        finally:
            await conn.close()

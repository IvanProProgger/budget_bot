import aiosqlite


from config.config import Config
from config.logging_config import logger


class ApprovalDB:
    """База данных для хранения данных о заявке"""

    def __init__(self):
        self.db_file = Config.database_path

    async def __aenter__(self):
        self._conn = await aiosqlite.connect(self.db_file)
        self._cursor = await self._conn.cursor()
        logger.info("Connected to database.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            await self._conn.close()
            logger.info("Disconnected from database.")
        return True

    async def create_table(self):
        """Создает таблицу 'approvals', если она еще не существует."""
        async with self:
            await self._cursor.execute(
                'SELECT name FROM sqlite_master WHERE type="table" AND name="approvals";'
            )
            table_exists = await self._cursor.fetchone()

            if not table_exists:
                try:
                    await self._cursor.execute(
                        """CREATE TABLE IF NOT EXISTS approvals
                                                  (id INTEGER PRIMARY KEY, 
                                                   amount REAL, 
                                                   expense_item TEXT, 
                                                   expense_group TEXT, 
                                                   partner TEXT, 
                                                   comment TEXT,
                                                   period TEXT, 
                                                   payment_method TEXT, 
                                                   approvals_needed INTEGER, 
                                                   approvals_received INTEGER,
                                                   status TEXT,
                                                   approved_by TEXT)"""
                    )
                    await self._conn.commit()
                    logger.info("Таблица 'approvals' создана.")
                except Exception as e:
                    raise RuntimeError(e)
            else:
                logger.info("Таблица 'approvals' уже существует.")


    async def insert_record(self, record):
        """
        Вставляет новую запись в таблицу 'approvals'.
        """
        try:
            await self._cursor.execute(
                "INSERT INTO approvals (amount, expense_item, expense_group, partner, comment, period, payment_method,"
                "approvals_needed, approvals_received, status, approved_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                list(record.values()),
            )
            await self._conn.commit()
            logger.info("Record inserted successfully.")
            return self._cursor.lastrowid
        except Exception as e:
            raise RuntimeError(f"Failed to insert record: {e}")

    async def get_row_by_id(self, row_id):
        try:
            result = await self._cursor.execute(
                "SELECT * FROM approvals WHERE id=?", (row_id,)
            )
            row = await result.fetchone()
            if row is None:
                return None
            logger.info("Row data received successfully")
            return dict(
                zip(
                    (
                        "id",
                        "amount",
                        "expense_item",
                        "expense_group",
                        "partner",
                        "comment",
                        "period",
                        "payment_method",
                        "approvals_needed",
                        "approvals_received",
                        "status",
                        "approved_by",
                    ),
                    row,
                )
            )
        except Exception as e:
            raise RuntimeError(f"Failed to fetch record: {e}")

    async def update_row_by_id(self, row_id, updates):
        try:
            await self._cursor.execute(
                "UPDATE approvals SET {} WHERE id = ?".format(
                    ", ".join([f"{key} = ?" for key in updates.keys()])
                ),
                list(updates.values()) + [row_id],
            )
            await self._conn.commit()
            logger.info("Record updated successfully.")
        except Exception as e:
            raise RuntimeError(f"Failed to update record: {e}. Approval ID: {row_id}, Updates: {updates}")

    async def find_not_paid(self):
        try:
            result = await self._cursor.execute(
                "SELECT * FROM approvals WHERE status != ? AND status != ?",
                ("Paid", "Rejected"),
            )
            rows = await result.fetchall()
            if not rows:
                return []
            logger.info("Not paid records found successfully.")

            return [
                dict(
                    zip(
                        (
                            "id заявки",
                            "сумма",
                            "статья",
                            "группа",
                            "партнёр",
                            "комментарий",
                            "период дат",
                            "способ оплаты",
                            "апрувов требуется",
                            "апрувов получено",
                            "статус",
                            "кем апрувенно",
                        ),
                        row,
                    )
                )
                for row in rows
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to fetch records: {e}")

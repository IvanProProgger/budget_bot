import aiosqlite

from config.config import Config
from config.logging_config import logger


class ApprovalDB:
    """База данных для хранения данных о заявке"""

    def __init__(self):
        self.db_file = Config.database_path

    async def __aenter__(self) -> 'ApprovalDB':
        self._conn = await aiosqlite.connect(self.db_file)
        self._cursor = await self._conn.cursor()
        logger.info("Connected to database.")
        return self

    async def __aexit__(self, exc_type: any, exc_val: any, exc_tb: any) -> bool:
        if exc_type:
            logger.error(f"Произошла ошибка: {exc_type}; {exc_val}; {exc_tb}")
        if self._conn:
            await self._conn.close()
            logger.info("Disconnected from database.")
        return True

    async def create_table(self) -> None:
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


    async def insert_record(self, record: dict[str, any]) -> int:
        """
        Добавляет новую запись в таблицу 'approvals'.

        Args:
            record (dict[str, any]): Словарь с данными для вставки.

        Returns:
            int: ID вставленной записи.
        """
        try:
            await self._cursor.execute(
                "INSERT INTO approvals (amount, expense_item, expense_group, partner, comment, period, payment_method,"
                "approvals_needed, approvals_received, status, approved_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                list(record.values()),
            )
            await self._conn.commit()
            logger.info("Запись добавлена успешно.")
            return self._cursor.lastrowid
        except Exception as e:
            raise RuntimeError(f"Не удалось добавить запись: {e}")

    async def get_row_by_id(self, row_id: int) -> dict[str, any] | None:
        """Получаем словарь из названий и значений столбцов по id"""
        try:
            result = await self._cursor.execute(
                "SELECT * FROM approvals WHERE id=?", (row_id,)
            )
            row = await result.fetchone()
            if row is None:
                return None
            logger.info("Данные строки получены успешно")
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
            raise RuntimeError(f"Не удалось получить запись: {e}")

    async def update_row_by_id(self, row_id: int, updates: dict[str, any]) -> None:
        """Функция меняет значения столбцов.
        :param принимает id строки row_id и словарь updates из названий и значений столбцов"""
        try:
            await self._cursor.execute(
                "UPDATE approvals SET {} WHERE id = ?".format(
                    ", ".join([f"{key} = ?" for key in updates.keys()])
                ),
                list(updates.values()) + [row_id],
            )
            await self._conn.commit()
            logger.info("Запись обновлена успешно.")
        except Exception as e:
            raise RuntimeError(f"Не удалось обновить запись: {e}. ID заявки: {row_id}, Обновления: {updates}")

    async def find_not_paid(self) -> list[dict[str, str]]:
        """Функция возвращает все данные по всем неоплаченным заявкам на платёж"""
        try:
            result = await self._cursor.execute(
                "SELECT * FROM approvals WHERE status != ? AND status != ?",
                ("Paid", "Rejected"),
            )
            rows = await result.fetchall()
            if not rows:
                return []
            logger.info("Неоплаченные записи успешно найдены.")

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
            raise RuntimeError(f"Не удалось получить записи: {e}")
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from flet import *
import threading
import plyer


def init_db():
     """
    Инициализация базы данных
    Создание таблиц notes, lists и list_items
    """
     conn = sqlite3.connect('tasks.db')
     cursor = conn.cursor()

     # Таблица заметок (без изменений)
     cursor.execute('''CREATE TABLE IF NOT EXISTS notes 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT, 
                    content TEXT,
                    priority TEXT,
                    color TEXT,
                    created DATETIME,
                    completed BOOLEAN DEFAULT 0,
                    deleted_at DATETIME,
                    reminder_time DATETIME)''')

     # Обновленная таблица списков с правильными столбцами
     cursor.execute('''CREATE TABLE IF NOT EXISTS lists 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    description TEXT,
                    color TEXT,
                    priority TEXT,
                    created DATETIME,
                    completed BOOLEAN DEFAULT 0,
                    deleted_at DATETIME)''')

     # Таблица элементов списка
     cursor.execute('''CREATE TABLE IF NOT EXISTS list_items 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_id INTEGER,
                    text TEXT,
                    is_completed BOOLEAN DEFAULT 0,
                    FOREIGN KEY(list_id) REFERENCES lists(id))''')

     conn.commit()
     conn.close()


class ReminderManager:
     """
    Класс для управления напоминаниями в фоновом режиме
    """

     def __init__(self):
          """
        Инициализация менеджера напоминаний
        Создание потока и события для управления проверкой напоминаний
        """
          self.stop_event = threading.Event()
          self.reminder_thread = None
          self.logger = self._setup_logger()

     def _setup_logger(self):
          """
        Настройка логирования для менеджера напоминаний
        """
          logger = logging.getLogger('ReminderManager')
          logger.setLevel(logging.INFO)

          # Создание обработчика для записи в файл
          file_handler = logging.FileHandler('reminder_log.txt', encoding='utf-8')
          file_handler.setLevel(logging.INFO)

          # Создание обработчика для вывода в консоль
          console_handler = logging.StreamHandler()
          console_handler.setLevel(logging.INFO)

          # Формат логов
          formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
          file_handler.setFormatter(formatter)
          console_handler.setFormatter(formatter)

          # Добавление обработчиков
          logger.addHandler(file_handler)
          logger.addHandler(console_handler)

          return logger

     def start_reminder_check(self):
          """
        Запуск потока проверки напоминаний
        Останавливает существующий поток и запускает новый
        """
          try:
               # Остановка существующего потока
               if self.reminder_thread and self.reminder_thread.is_alive():
                    self.stop_event.set()
                    self.reminder_thread.join()

               # Сброс события остановки
               self.stop_event.clear()

               # Запуск нового потока для проверки напоминаний
               self.reminder_thread = threading.Thread(target=self._check_reminders, daemon=True)
               self.reminder_thread.start()

               self.logger.info("Поток проверки напоминаний запущен")
          except Exception as e:
               self.logger.error(f"Ошибка при запуске потока проверки напоминаний: {e}")

     def _check_reminders(self):
          """
        Внутренний метод проверки напоминаний
        Проверяет базу данных на наличие напоминаний и отправляет уведомления
        """
          while not self.stop_event.is_set():
               try:
                    # Подключение к базе данных
                    conn = sqlite3.connect('tasks.db')
                    cursor = conn.cursor()

                    # Получение текущего времени и поиск напоминаний
                    current_time = datetime.now()
                    cursor.execute('''
                SELECT id, title, content, reminder_time 
                FROM notes 
                WHERE reminder_time <= ? AND completed = 0 AND reminder_time IS NOT NULL
            ''', (current_time,))

                    due_reminders = cursor.fetchall()

                    # Отправка уведомлений для просроченных напоминаний
                    for reminder in due_reminders:
                         try:
                              # Отправка системного уведомления
                              plyer.notification.notify(
                                   title=f"Напоминание: {reminder[1]}",
                                   message=reminder[2],
                                   timeout=10
                              )

                              self.logger.info(f"Отправлено напоминание: {reminder[1]}")

                              # Пометка напоминания как выполненного
                              cursor.execute('''
                        UPDATE notes 
                        SET completed = 1 
                        WHERE id = ?
                    ''', (reminder[0],))
                         except Exception as notify_error:
                              self.logger.error(f"Ошибка при отправке уведомления: {notify_error}")

                    conn.commit()
                    conn.close()

                    # Ожидание минуты перед следующей проверкой
                    self.stop_event.wait(60)

               except sqlite3.Error as db_error:
                    self.logger.error(f"Ошибка базы данных при проверке напоминаний: {db_error}")
                    # Ожидание перед повторной попыткой
                    self.stop_event.wait(60)

               except Exception as e:
                    self.logger.error(f"Неожиданная ошибка при проверке напоминаний: {e}")
                    # Ожидание перед повторной попыткой
                    self.stop_event.wait(60)

     def stop_reminder_check(self):
          """
        Остановка потока проверки напоминаний
        """
          try:
               if self.reminder_thread:
                    self.stop_event.set()
                    self.reminder_thread.join()
                    self.logger.info("Поток проверки напоминаний остановлен")
          except Exception as e:
               self.logger.error(f"Ошибка при остановке потока проверки напоминаний: {e}")


class ListManager:
    def __init__(self, page, tab_container=None):
        self.page = page
        self.tab_container = tab_container
        self.current_list_id = None

        # Приоритеты списков с серыми оттенками
        self.priority_levels = {
            'Низкий': colors.GREY_600,
            'Средний': colors.GREY_700,
            'Высокий': colors.GREY_800
        }

        # Основные элементы интерфейса
        self.list_title_input = TextField(
            label="Название списка",
            width=600,
            hint_text="Введите название списка",
            border_color=colors.GREY_700,
            focused_border_color=colors.GREY_600,
            capitalization=TextCapitalization.WORDS,
            color=colors.WHITE
        )

        self.list_description_input = TextField(
            label="Описание списка",
            width=600,
            multiline=True,
            min_lines=2,
            max_lines=4,
            hint_text="Краткое описание списка (необязательно)",
            border_color=colors.GREY_700,
            focused_border_color=colors.GREY_600,
            color=colors.WHITE
        )

        self.list_priority_dropdown = Dropdown(
            label="Приоритет списка",
            width=400,
            border_color=colors.GREY_700,
            focused_border_color=colors.GREY_600,
            options=[dropdown.Option(priority) for priority in self.priority_levels.keys()],
            color=colors.WHITE
        )

        # Новые элементы для поиска и фильтрации
        self.search_input = TextField(
            label="Поиск списков",
            width=600,
            hint_text="Введите название или описание списка",
            on_change=self.perform_search,
            border_color=colors.GREY_700,
            focused_border_color=colors.GREY_600,
            color=colors.WHITE
        )

        self.sort_dropdown = Dropdown(
            label="Сортировка",
            width=300,
            options=[
                dropdown.Option("По дате создания"),
                dropdown.Option("По названию"),
                dropdown.Option("По приоритету")
            ],
            on_change=self.perform_search,
            border_color=colors.GREY_700,
            focused_border_color=colors.GREY_600,
            color=colors.WHITE
        )

        self.priority_filter = Dropdown(
            label="Фильтр приоритета",
            width=300,
            options=[
                dropdown.Option("Все"),
                dropdown.Option("Низкий"),
                dropdown.Option("Средний"),
                dropdown.Option("Высокий")
            ],
            on_change=self.perform_search,
            border_color=colors.GREY_700,
            focused_border_color=colors.GREY_600,
            color=colors.WHITE
        )

        # Создаем отдельный контейнер для создания нового списка
        self.new_list_items_container = Column(
            spacing=10,
            scroll=ScrollMode.AUTO,
            width=600
        )

        # Список для хранения элементов существующих списков
        self.list_items_container = Column(
            spacing=10,
            scroll=ScrollMode.AUTO,
            width=600
        )

        # Поле для добавления нового элемента
        self.new_item_input = TextField(
            label="Новый элемент списка",
            width=500,
            hint_text="Введите текст элемента",
            border_color=colors.GREY_700,
            focused_border_color=colors.GREY_600,
            capitalization=TextCapitalization.SENTENCES,
            color=colors.WHITE
        )

        self.list_items_container = Column(
             spacing=10,
             scroll=ScrollMode.AUTO,
             width=600
        )

        # Список для хранения элементов
        self.list_items = []
        self.load_lists()

    def load_lists(self, tab_name="Списки"):
         """
         Загрузка списков для конкретной вкладки
         """
         try:
              conn = sqlite3.connect('tasks.db')
              cursor = conn.cursor()

              # Получаем списки только для этой вкладки
              cursor.execute('''
                 SELECT id, title, description, color, priority, created 
                 FROM lists 
                 WHERE completed = 0 
                 ORDER BY created DESC
             ''')
              lists = cursor.fetchall()

              # Очистка текущего контейнера
              self.list_items_container.controls.clear()

              # Создание визуальных элементов для каждого списка
              for list_id, title, description, color, priority, created in lists:
                   # Получаем элементы списка
                   cursor.execute('''
                     SELECT text, is_completed 
                     FROM list_items 
                     WHERE list_id = ?
                 ''', (list_id,))
                   list_items = cursor.fetchall()

                   # Создаем контейнер для элементов списка с чекбоксами
                   items_column = Column()
                   for item_text, is_completed in list_items:
                        item_checkbox = Checkbox(
                             label=item_text,
                             value=bool(is_completed),
                             on_change=lambda e, lid=list_id, text=item_text: self.toggle_list_item(e, lid, text),
                             label_style=TextThemeStyle.BODY_SMALL if is_completed else TextThemeStyle.BODY_MEDIUM,
                             active_color=colors.GREY_700 if is_completed else colors.GREY_600
                        )
                        items_column.controls.append(item_checkbox)

                   # Создаем карточку списка
                   list_card = Container(
                        width=600,
                        padding=10,
                        border_radius=10,
                        gradient=LinearGradient(
                             begin=alignment.center_left,
                             end=alignment.center_right,
                             colors=[colors.GREY_900, colors.GREY_800]
                        ),
                        content=Column([
                             Text(title, size=18, weight=FontWeight.BOLD, color=colors.WHITE),
                             Text(description or "", size=12, color=colors.GREY_600),
                             Row([
                                  Text(f"Приоритет: {priority}",
                                       color=self.priority_levels.get(priority, colors.GREY_600)),
                                  Text(f"Создан: {created}", color=colors.GREY_600)
                             ], alignment='spaceBetween'),
                             items_column
                        ])
                   )

                   # Добавляем действия для редактирования и удаления
                   list_card.data = {
                        'list_id': list_id,
                        'title': title,
                        'description': description,
                        'priority': priority
                   }

                   list_card.on_click = self.edit_list_with_data

                   # Добавляем кнопки действий
                   actions_row = Row([
                        IconButton(
                             icon=icons.EDIT,
                             icon_color=colors.GREY_600,
                             on_click=self.edit_list_with_data,
                             data={'list_id': list_id}
                        ),
                        IconButton(
                             icon=icons.DELETE,
                             icon_color=colors.GREY_600,
                             on_click=self.delete_list_with_data,
                             data={'list_id': list_id}
                        )
                   ])

                   list_card.content.controls.append(actions_row)

                   self.list_items_container.controls.append(list_card)

              conn.close()
              self.page.update()

         except sqlite3.Error as e:
              print(f"Ошибка при загрузке списков: {e}")
              self.show_notification(f"Ошибка загрузки: {e}")

    def toggle_list_item(self, e, list_id, item_text):
         """
         Обновление статуса элемента списка
         """
         try:
              conn = sqlite3.connect('tasks.db')
              cursor = conn.cursor()

              # Обновляем статус элемента
              cursor.execute('''
                 UPDATE list_items 
                 SET is_completed = ? 
                 WHERE list_id = ? AND text = ?
             ''', (e.control.value, list_id, item_text))

              conn.commit()
              conn.close()

              # Обновляем визуальное представление
              e.control.label_style = (
                   TextThemeStyle.BODY_SMALL if e.control.value
                   else TextThemeStyle.BODY_MEDIUM
              )
              e.control.active_color = (
                   colors.GREY_700 if e.control.value
                   else colors.GREY_600
              )
              self.page.update()

         except sqlite3.Error as e:
              print(f"Ошибка при обновлении элемента списка: {e}")
              self.show_notification(f"Ошибка обновления: {e}")

    def edit_list_with_data(self, e):
         """
         Обработчик редактирования списка с использованием data
         """
         list_data = e.control.data if hasattr(e.control, 'data') else e.control.parent.parent.data
         self.edit_list(list_data['list_id'])

    def delete_list_with_data(self, e):
         """
         Обработчик удаления списка с использованием data
         """
         list_id = e.control.data['list_id']
         self.delete_list(list_id)

    def edit_list(self, list_id):
         """
         Редактирование существующего списка
         """
         try:
              conn = sqlite3.connect('tasks.db')
              cursor = conn.cursor()

              # Получаем данные списка
              cursor.execute('SELECT title, description, priority FROM lists WHERE id = ?', (list_id,))
              list_data = cursor.fetchone()

              # Получаем элементы списка
              cursor.execute('SELECT text, is_completed FROM list_items WHERE list_id = ?', (list_id,))
              items = cursor.fetchall()

              # Заполняем поля формы
              self.list_title_input.value = list_data[0]
              self.list_description_input.value = list_data[1] or ""
              self.list_priority_dropdown.value = list_data[2]

              # Очищаем текущие элементы
              self.list_items.clear()
              self.new_list_items_container.controls.clear()

              # Добавляем элементы списка
              for item_text, is_completed in items:
                   # Эмулируем добавление элемента
                   self.new_item_input.value = item_text
                   self.add_list_item()

                   # Устанавливаем статус выполнения
                   last_item = self.list_items[-1]
                   last_item['is_completed'] = bool(is_completed)
                   last_item['checkbox'].value = bool(is_completed)

                   # Обновляем визуализацию
                   if is_completed:
                        last_item['ui_element'].gradient = LinearGradient(
                             begin=alignment.center_left,
                             end=alignment.center_right,
                             colors=[colors.GREY_800, colors.GREY_700]
                        )
                        last_item['ui_element'].content.controls[0].label = f"✓ {item_text}"
                        last_item['ui_element'].content.controls[0].disabled = True

              # Устанавливаем текущий редактируемый список
              self.current_list_id = list_id

              conn.close()
              self.page.update()

         except sqlite3.Error as e:
              print(f"Ошибка при редактировании списка: {e}")
              self.show_notification(f"Ошибка редактирования: {e}")

    def delete_list(self, list_id):
         """
         Удаление списка с анимацией
         """
         try:
              conn = sqlite3.connect('tasks.db')
              cursor = conn.cursor()

              # Удаляем элементы списка
              cursor.execute('DELETE FROM list_items WHERE list_id = ?', (list_id,))

              # Удаляем сам список
              cursor.execute('DELETE FROM lists WHERE id = ?', (list_id,))

              conn.commit()
              conn.close()

              # Обновляем визуальный список
              self.load_lists()

              # Показываем уведомление
              self.show_notification("Список успешно удален")

         except sqlite3.Error as e:
              print(f"Ошибка при удалении списка: {e}")
              self.show_notification(f"Ошибка удаления: {e}")

    def add_list_item(self, e=None):
        """
        Улучшенное добавление элемента в список
        """
        if not self.new_item_input.value.strip():
            return

        # Создаем уникальный идентификатор
        item_id = str(len(self.list_items))

        # Создание элемента с анимацией и улучшенным дизайном
        item_row = Container(
            data=item_id,
            border_radius=10,
            padding=5,
            animate=animation.Animation(300, "ease"),
            content=Row([
                Checkbox(
                    label=self.new_item_input.value,
                    value=False,
                    on_change=self.toggle_item_status,
                    active_color=colors.GREY_600,
                    check_color=colors.WHITE
                ),
                IconButton(
                    icon=icons.DELETE_OUTLINE,
                    icon_color=colors.GREY_700,
                    data=item_id,
                    on_click=self.remove_list_item,
                    tooltip="Удалить элемент"
                )
            ], alignment='spaceBetween'),
            gradient=LinearGradient(
                begin=alignment.center_left,
                end=alignment.center_right,
                colors=[colors.GREY_900, colors.GREY_800]
            )
        )

        # Добавление с плавной анимацией
        self.new_list_items_container.controls.append(item_row)
        self.list_items.append({
            'text': self.new_item_input.value,
            'is_completed': False,
            'ui_element': item_row,
            'id': item_id,
            'checkbox': item_row.content.controls[0]
        })

        # Очистка и анимация поля ввода
        self.new_item_input.value = ""
        self.new_item_input.border_color = colors.GREY_600

        # Явное обновление контейнера и страницы
        self.new_list_items_container.update()
        self.page.update()

    def remove_list_item(self, e):
        """
        Удаление элемента из списка с анимацией
        """
        try:
            # Получаем идентификатор элемента из события
            item_id = e.control.data

            # Находим и удаляем элемент из визуального контейнера
            for control in self.new_list_items_container.controls[:]:
                if control.data == item_id:
                    # Анимация исчезновения
                    control.opacity = 0
                    control.scale = 0.5
                    self.page.update()
                    time.sleep(0.3)  # Небольшая задержка для анимации
                    self.new_list_items_container.controls.remove(control)
                    break

            # Удаляем из логического списка
            self.list_items = [
                item for item in self.list_items
                if item['id'] != item_id
            ]

            self.page.update()
        except Exception as ex:
            print(f"Ошибка при удалении элемента: {ex}")

    def toggle_item_status(self, e):
        """
        Улучшенное переключение статуса элемента
        """
        checkbox = e.control
        for item in self.list_items:
            if item['text'] == checkbox.label:
                item['is_completed'] = checkbox.value

                # Расширенная визуализация
                if checkbox.value:
                    item['ui_element'].gradient = LinearGradient(
                        begin=alignment.center_left,
                        end=alignment.center_right,
                        colors=[colors.GREY_800, colors.GREY_700]
                    )
                    item['ui_element'].content.controls[0].label = f"✓ {item['text']}"
                    item['ui_element'].content.controls[0].disabled = True
                else:
                    item['ui_element'].gradient = LinearGradient(
                        begin=alignment.center_left,
                        end=alignment.center_right,
                        colors=[colors.GREY_900, colors.GREY_800]
                    )
                    item['ui_element'].content.controls[0].label = item['text']
                    item['ui_element'].content.controls[0].disabled = False

                break
        self.page.update()

    def save_list(self, e=None):
        """
        Сохранение списка в базу данных с расширенной обработкой ошибок
        """
        # Валидация обязательных полей
        if not self.list_title_input.value:
            self.show_notification("Название списка не может быть пустым", color=colors.GREY_800)
            return

        # Проверка наличия элементов в списке
        if not self.list_items:
            self.show_notification("Добавьте хотя бы один элемент в список", color=colors.GREY_700)
            return

        try:
            conn = sqlite3.connect('tasks.db')
            cursor = conn.cursor()

            # Проверяем, создаем новый список или обновляем существующий
            if self.current_list_id is None:
                # Создание нового списка
                cursor.execute('''
                    INSERT INTO lists 
                    (title, description, color, priority, created, completed) 
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    self.list_title_input.value,
                    self.list_description_input.value or "",
                    "Темный",  # Фиксированный серый цвет
                    self.list_priority_dropdown.value or "Низкий",
                    datetime.now(),
                    0
                ))
                list_id = cursor.lastrowid
            else:
                # Обновление существующего списка
                cursor.execute('''
                    UPDATE lists 
                    SET title=?, description=?, color=?, priority=? 
                    WHERE id=?
                ''', (
                    self.list_title_input.value,
                    self.list_description_input.value or "",
                    "Темный",  # Фиксированный серый цвет
                    self.list_priority_dropdown.value or "Низкий",
                    self.current_list_id
                ))
                list_id = self.current_list_id

            # Сохранение элементов списка
            # Сначала удаляем существующие элементы
            cursor.execute('DELETE FROM list_items WHERE list_id = ?', (list_id,))

            # Добавляем новые элементы
            for item in self.list_items:
                cursor.execute('''
                    INSERT INTO list_items 
                    (list_id, text, is_completed) 
                    VALUES (?, ?, ?)
                ''', (
                    list_id,
                    item['text'],
                    item['is_completed']
                ))

            # Явное подтверждение транзакции
            conn.commit()

            # Показываем успешное уведомление
            self.show_notification("Список успешно сохранен")

            # Очистка полей после сохранения
            self.reset_list_form()

            # ВАЖНОЕ ИЗМЕНЕНИЕ: Сбрасываем текущий редактируемый список
            self.current_list_id = None

        except sqlite3.Error as e:
            # Подробное логирование ошибки базы данных
            print(f"Ошибка SQLite при сохранении списка: {e}")
            self.show_notification(f"Ошибка при сохранении: {e}", color=colors.GREY_800)
        except Exception as ex:
            # Обработка непредвиденных ошибок
            print(f"Неожиданная ошибка при сохранении списка: {ex}")
            self.show_notification(f"Непредвиденная ошибка: {ex}", color=colors.GREY_800)

    def reset_list_form(self):
        """
        Сброс всех полей формы списка
        """
        # Очистка полей ввода
        self.list_title_input.value = ""
        self.list_description_input.value = ""

        # Сброс выпадающего списка приоритетов
        self.list_priority_dropdown.value = "Низкий"

        # Очистка списка элементов
        self.list_items.clear()
        self.new_list_items_container.controls.clear()

        # Обновление страницы
        self.page.update()

    def show_notification(self, message, color=colors.GREY_800):
        """
        Улучшенный метод показа уведомлений
        """
        try:
            snack_bar = SnackBar(
                content=Text(message, color=colors.WHITE),
                bgcolor=color,
                duration=3000
            )
            self.page.overlay.append(snack_bar)
            snack_bar.open = True
            self.page.update()
        except Exception as e:
            print(f"Ошибка при показе уведомления: {e}")

    def perform_search(self, e=None):
        """
        Выполнение поиска и фильтрации списков
        """
        search_query = self.search_input.value.lower().strip()
        sort_option = self.sort_dropdown.value
        priority_filter = self.priority_filter.value

        try:
            conn = sqlite3.connect('tasks.db')
            cursor = conn.cursor()

            # Базовый SQL-запрос с возможностью фильтрации
            query = '''
                SELECT id, title, description, color, priority, created 
                FROM lists 
                WHERE completed = 0 
            '''
            params = []

            # Добавление поиска по названию или описанию
            if search_query:
                query += ' AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ?)'
                params.extend([f'%{search_query}%', f'%{search_query}%'])

            # Фильтрация по приоритету
            if priority_filter and priority_filter != "Все":
                query += ' AND priority = ?'
                params.append(priority_filter)

            # Сортировка
            if sort_option == "По дате создания":
                query += ' ORDER BY created DESC'
            elif sort_option == "По названию":
                query += ' ORDER BY title ASC'
            elif sort_option == "По приоритету":
                query += ' ORDER BY CASE priority WHEN "Высокий" THEN 1 WHEN "Средний" THEN 2 ELSE 3 END'

            cursor.execute(query, params)
            lists = cursor.fetchall()

            # Очистка текущего контейнера
            self.list_items_container.controls.clear()

            # Создание визуальных элементов для каждого списка
            for list_id, title, description, color, priority, created in lists:
                list_card = Container(
                    width=600,
                    padding=10,
                    border_radius=10,
                    gradient=LinearGradient(
                        begin=alignment.center_left,
                        end=alignment.center_right,
                        colors=[colors.GREY_900, colors.GREY_800]
                    ),
                    content=Column([
                        Text(title, size=18, weight=FontWeight.BOLD, color=colors.WHITE),
                        Text(description or "", size=12, color=colors.GREY_600),
                        Row([
                            Text(f"Приоритет: {priority}", color=self.priority_levels.get(priority, colors.GREY_600)),
                            Text(f"Создан: {created}", color=colors.GREY_600)
                        ], alignment='spaceBetween')
                    ])
                )
                self.list_items_container.controls.append(list_card)

            conn.close()
            self.page.update()

        except sqlite3.Error as e:
            print(f"Ошибка при поиске списков: {e}")
            self.show_notification(f"Ошибка поиска: {e}")

    def create_list_tab(self):
         """
	    Создание вкладки для создания нового списка
	    """
         return Container(
              bgcolor=colors.GREY_900,
              border_radius=15,
              padding=20,
              content=Column([
                   # Заголовок и описание с улучшенным дизайном
                   Text("Создание списка", size=24, weight=FontWeight.BOLD, color=colors.WHITE),

                   self.list_title_input,
                   self.list_description_input,

                   # Приоритет с улучшенным дизайном
                   self.list_priority_dropdown,

                   # Добавление элементов списка с анимацией
                   Row([
                        self.new_item_input,
                        IconButton(
                             icon=icons.ADD_CIRCLE,
                             icon_color=colors.GREY_600,
                             on_click=self.add_list_item,
                             tooltip="Добавить элемент",
                             style=ButtonStyle(
                                  shape=RoundedRectangleBorder(radius=10)
                             )
                        )
                   ]),

                   # Контейнер для элементов с улучшенным дизайном
                   Container(
                        width=600,
                        height=250,
                        content=self.new_list_items_container,
                        border=border.all(2, colors.GREY_800),
                        border_radius=15,
                        gradient=LinearGradient(
                             begin=alignment.center_left,
                             end=alignment.center_right,
                             colors=[colors.GREY_900, colors.GREY_800]
                        )
                   ),

                   # Кнопка сохранения с анимацией
                   ElevatedButton(
                        "Сохранить список",
                        on_click=self.save_list,
                        style=ButtonStyle(
                             bgcolor=colors.GREY_800,
                             color=colors.WHITE,
                             shape=RoundedRectangleBorder(radius=15)
                        ),
                        animate_scale=True
                   )
              ], horizontal_alignment='center', spacing=15)
         )


class Notes:
     """
          Класс для управления заметками
          """

     def __init__(self, page: Page):
          """
          Инициализация класса Notes
          Настройка интерфейса и компонентов для работы с заметками
          """
          self.page = page
          self.reminder_manager = ReminderManager()

          # Цветовая палитра
          self.color_palette = {
               'Темный': colors.GREY_900,
               'Светлый': colors.GREY_200,
               'Зеленый': colors.GREEN_600,
               'Красный': colors.RED_600,
               'Фиолетовый': colors.DEEP_PURPLE_600,
               'Голубой': colors.BLUE_600,
               'Белый': colors.WHITE
          }

          # Список заметок
          self.notes_list = ListView(expand=True, spacing=10, padding=20)

          # Добавление выбора даты напоминания
          self.reminder_datetime = DatePicker(
               first_date=datetime.now(),
               last_date=datetime.now() + timedelta(days=365),
               on_change=self.on_date_change
          )

          # Добавление выбора времени напоминания
          self.reminder_time = TimePicker(
               on_change=self.on_time_change
          )

          # Поле поиска
          self.search_input = TextField(
               label="Поиск заметок",
               width=600,
               on_change=self.perform_search
          )

          # Фильтр приоритета
          self.priority_filter = Dropdown(
               label="Приоритет",
               options=[
                    dropdown.Option("Все"),
                    dropdown.Option("Низкий"),
                    dropdown.Option("Средний"),
                    dropdown.Option("Высокий")
               ],
               width=300,
               on_change=self.perform_search
          )

          # Фильтр цвета
          self.color_filter = Dropdown(
               label="Цвет",
               options=[dropdown.Option("Все")] +
                       [dropdown.Option(color) for color in self.color_palette.keys()],
               width=300,
               on_change=self.perform_search
          )

          # Выпадающий список приоритетов для создания заметки
          self.priority_dropdown = Dropdown(
               label="Степень важности",
               options=[
                    dropdown.Option("Низкий"),
                    dropdown.Option("Средний"),
                    dropdown.Option("Высокий")
               ],
               width=300
          )

          # Выпадающий список цветов для создания заметки
          self.color_dropdown = Dropdown(
               label="Цвет заметки",
               options=[dropdown.Option(color) for color in self.color_palette.keys()],
               width=300
          )

          # Поле ввода заголовка
          self.title_input = TextField(label="Заголовок", width=600)

          # Поле ввода содержимого
          self.content_input = TextField(
               label="Содержание",
               multiline=True,
               min_lines=5,
               max_lines=10,
               width=600
          )

          # Ссылки для редактирования заметки
          self.edit_title_input = Ref[TextField]()
          self.edit_content_input = Ref[TextField]()
          self.edit_priority_dropdown = Ref[Dropdown]()
          self.edit_color_dropdown = Ref[Dropdown]()

          # Для сохранения текущей редактируемой заметки
          self.current_note_id = None

          # Создаем экземпляр ListManager для обычных списков
          self.list_manager = ListManager(page)

          # Создаем экземпляр ListsManager для списков задач
          self.lists_manager = ListManager(page)

          # Модальное окно для напоминания
          self.reminder_modal = BottomSheet(
               Container(
                    width=600,
                    padding=20,
                    content=Column([
                         Text("Настройка напоминания", size=20, weight=FontWeight.BOLD),
                         self.reminder_datetime,
                         self.reminder_time,
                         ElevatedButton(
                              "Сохранить напоминание",
                              on_click=self.save_reminder,
                              bgcolor=colors.BLUE_600,
                              color=colors.WHITE
                         )
                    ], horizontal_alignment='center')
               )
          )

          # Модальное окно для создания заметки
          self.note_modal = BottomSheet(
               Container(
                    width=800,  # Увеличена ширина
                    height=700,  # Добавлена фиксированная высота
                    padding=20,
                    content=Column(
                         [
                              Tabs(
                                   selected_index=0,
                                   width=760,  # Ширина табов
                                   tabs=[
                                        Tab(
                                             text="Заметка",
                                             content=Container(
                                                  content=Column(
                                                       [self.create_note_tab()],
                                                       scroll='auto',  # Прокрутка для первой вкладки
                                                       height=600
                                                  )
                                             )
                                        ),
                                        Tab(
                                             text="Список",
                                             content=Container(
                                                  content=Column(
                                                       [self.list_manager.create_list_tab()],
                                                       scroll='auto',  # Прокрутка для второй вкладки
                                                       height=600
                                                  )
                                             )
                                        )
                                   ]
                              )
                         ],
                         horizontal_alignment='center',
                         scroll='auto'  # Прокрутка всего контейнера
                    )
               )
          )

     def create_search_container(self):
          """
             Создание панели поиска и фильтрации для вкладки 'Мои списки'
             """
          return Container(
               width=600,
               padding=10,
               border_radius=10,
               bgcolor=colors.GREY_900,
               content=Column([
                    Row([
                         self.search_input,
                         self.sort_dropdown,
                         self.priority_filter
                    ], wrap=True, spacing=10)
               ])
          )

     def on_date_change(self, e):
          """
        Обработчик изменения даты
        """
          print(f"Выбранная дата: {e.control.value}")
          self.page.update()

     def load_lists(self):
          """Загрузка списков из базы данных"""
          self.notes_list.controls.clear()

          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               cursor.execute('SELECT * FROM lists WHERE completed = 0 ORDER BY created DESC')
               lists = cursor.fetchall()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка при загрузке списков: {e}"))
               self.page.snack_bar.open = True
               return
          finally:
               conn.close()

          for list_item in lists:
               # Загрузка элементов списка
               try:
                    conn = sqlite3.connect('tasks.db')
                    cursor = conn.cursor()
                    cursor.execute('SELECT text, is_completed FROM list_items WHERE list_id = ?', (list_item[0],))
                    list_contents = cursor.fetchall()
               except sqlite3.Error as e:
                    print(f"Ошибка при загрузке элементов списка: {e}")
                    list_contents = []
               finally:
                    conn.close()

               # Форматирование времени напоминания
               reminder_text = self._format_reminder_time(list_item[7])

               # Создание контейнера для списка
               list_container = Container(
                    width=850,
                    padding=10,
                    bgcolor=self.color_palette.get(list_item[2], colors.WHITE70),
                    border_radius=10,
                    content=Column([
                         Text(f"Приоритет: {list_item[3]}", weight=FontWeight.BOLD),
                         Text(list_item[1], size=18, weight=FontWeight.W_600),
                         Column([
                              Checkbox(label=item[0], value=bool(item[1])) for item in list_contents
                         ]),
                         Row([
                              Text(f"Создано: {list_item[4]}", size=10, color=colors.BLACK54),
                              Text(reminder_text, size=10, color=colors.BLACK54),
                              Row([
                                   IconButton(
                                        icon=icons.EDIT,
                                        icon_color=colors.BLUE,
                                        on_click=lambda e, list_data=list_item: self.edit_list(list_data)
                                   ),
                                   IconButton(
                                        icon=icons.DELETE,
                                        icon_color=colors.RED,
                                        on_click=lambda e, list_id=list_item[0]: self.delete_list(list_id)
                                   )
                              ])
                         ])
                    ])
               )
               self.notes_list.controls.append(list_container)

          self.page.update()

     def edit_list(self, list_data):
          """Редактирование списка"""
          edit_modal = BottomSheet(
               Container(
                    width=600,
                    padding=20,
                    content=Column([
                         Text("Редактирование списка", size=20, weight=FontWeight.BOLD),
                         TextField(
                              label="Заголовок",
                              value=list_data[1],
                              width=600
                         ),
                         Dropdown(
                              label="Приоритет",
                              options=[
                                   dropdown.Option("Низкий"),
                                   dropdown.Option("Средний"),
                                   dropdown.Option("Высокий")
                              ],
                              value=list_data[3],
                              width=300
                         ),
                         Dropdown(
                              label="Цвет списка",
                              options=[dropdown.Option(color) for color in self.color_palette.keys()],
                              value=list_data[2],
                              width=300
                         )
                    ], horizontal_alignment='center')
               )
          )

          edit_modal.open = True
          self.page.overlay.append(edit_modal)
          self.page.update()

     def delete_list(self, list_id):
          """Удаление списка"""
          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               cursor.execute('UPDATE lists SET completed = 1, deleted_at = ? WHERE id = ?',
                              (datetime.now().isoformat(), list_id))
               conn.commit()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка при удалении: {e}"))
               self.page.snack_bar.open = True
          finally:
               conn.close()

          self.load_lists()
          self.page.update()

     def on_time_change(self, e):
          """
        Обработчик изменения времени
        """
          print(f"Выбранное время: {e.control.value}")
          self.page.update()

     def create_search_container(self):
          """
        Создание контейнера для поиска заметок
        """
          return Container(
               content=Column([
                    Row([
                         self.search_input
                    ], alignment='center'),
                    Row([
                         self.priority_filter,
                         self.color_filter
                    ], alignment='center')
               ]),
               padding=20
          )

     def perform_search(self, e=None):
          """
        Выполнение поиска заметок с фильтрацией
        """
          search_text = self.search_input.value.lower() if self.search_input.value else ""
          priority_filter = self.priority_filter.value if self.priority_filter.value != "Все" else None
          color_filter = self.color_filter.value if self.color_filter.value != "Все" else None

          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()

               query = '''
                SELECT * FROM notes 
                WHERE completed = 0 
                AND (
                    lower(title) LIKE ? OR 
                    lower(content) LIKE ?
                )
            '''
               params = [f'%{search_text}%', f'%{search_text}%']

               if priority_filter:
                    query += ' AND priority = ?'
                    params.append(priority_filter)

               if color_filter:
                    query += ' AND color = ?'
                    params.append(color_filter)

               query += ' ORDER BY created DESC'

               cursor.execute(query, params)
               notes = cursor.fetchall()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(
                    content=Text(f"Ошибка при поиске: {e}"),
                    bgcolor=colors.RED
               )
               self.page.snack_bar.open = True
               return
          finally:
               conn.close()

          self.notes_list.controls.clear()

          if not notes:
               no_results = Container(
                    content=Text(
                         "Заметки не найдены",
                         size=18,
                         color=colors.GREY
                    ),
                    alignment=alignment.center,
                    padding=20
               )
               self.notes_list.controls.append(no_results)
          else:
               for note in notes:
                    if note[7]:  # Если время напоминания существует
                         try:
                              reminder_datetime = datetime.fromisoformat(str(note[7]))
                              reminder_text = f"Напоминание: {reminder_datetime.strftime('%d.%m.%Y %H:%M')}"
                         except (ValueError, TypeError):
                              reminder_text = "Некорректное время напоминания"
                    else:
                         reminder_text = "Добавить напоминание"

                    note_container = Container(
                         width=850,
                         padding=10,
                         bgcolor=self.color_palette.get(note[4], colors.WHITE70),
                         border_radius=10,
                         content=Column([
                              Text(f"Приоритет: {note[3]}", weight=FontWeight.BOLD),
                              Text(note[1], size=18, weight=FontWeight.W_600),
                              Text(note[2], size=14),
                              Row([
                                   Text(f"Создано: {note[5]}", size=10, color=colors.BLACK54),
                                   Text(reminder_text, size=10, color=colors.BLACK54),
                                   Row([
                                        IconButton(
                                             icon=icons.EDIT,
                                             icon_color=colors.BLUE,
                                             on_click=lambda e, note_data=note: self.edit_note(note_data)
                                        ),
                                        IconButton(
                                             icon=icons.DELETE,
                                             icon_color=colors.RED,
                                             on_click=lambda e, note_id=note[0]: self.delete_note(note_id)
                                        ),
                                        IconButton(
                                             icon=icons.ALARM_ADD,
                                             icon_color=colors.GREEN,
                                             on_click=lambda e, note_id=note[0]: self.open_reminder_modal(note_id)
                                        )
                                   ])
                              ])
                         ])
                    )
                    self.notes_list.controls.append(note_container)

          self.page.update()

     def open_note_modal(self, e=None):
          """
          Открытие модального окна для создания заметки
          """
          try:
               print("Открытие модального окна заметки")  # Отладочное сообщение

               # Сбрасываем текущий редактируемый note_id
               self.current_note_id = None

               # Очищаем поля ввода
               self.title_input.value = ""
               self.content_input.value = ""
               self.priority_dropdown.value = "Низкий"
               self.color_dropdown.value = "Белый"

               # Открываем модальное окно
               self.note_modal.open = True
               self.page.overlay.append(self.note_modal)
               self.page.update()

               print("Модальное окно открыто успешно")  # Отладочное сообщение
          except Exception as ex:
               print(f"Ошибка при открытии модального окна: {ex}")  # Подробный вывод ошибки
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка: {ex}"))
               self.page.snack_bar.open = True
               self.page.update()

     def open_reminder_modal(self, note_id):
          """
         Открытие модального окна напоминания для конкретной заметки
         """
          self.current_note_id = note_id
          self.page.overlay.append(self.reminder_modal)
          self.reminder_modal.open = True
          self.page.update()

     def save_reminder(self, e):
          """
         Сохранение настроек напоминания
         """
          if not self.reminder_datetime.value or not self.reminder_time.value:
               self.page.snack_bar = SnackBar(
                    content=Text("Выберите дату и время напоминания"),
                    bgcolor=colors.RED
               )
               self.page.snack_bar.open = True
               return

          # Объединение даты и времени
          reminder_time = datetime.combine(
               self.reminder_datetime.value,
               self.reminder_time.value
          )

          # Сохраняем последний выбранный note_id
          if hasattr(self, 'current_note_id'):
               try:
                    conn = sqlite3.connect('tasks.db')
                    cursor = conn.cursor()
                    cursor.execute('''
                    UPDATE notes 
                    SET reminder_time = ?
                    WHERE id = ?
                ''', (reminder_time.isoformat(), self.current_note_id))
                    conn.commit()
               except sqlite3.Error as ex:
                    self.page.snack_bar = SnackBar(
                         content=Text(f"Ошибка при сохранении напоминания: {ex}"),
                         bgcolor=colors.RED
                    )
                    self.page.snack_bar.open = True
               finally:
                    conn.close()

               # Перезагрузка заметок
               self.load_notes()

               # Закрываем модальное окно
               self.reminder_modal.open = False
               self.page.update()

     def create_note_tab(self):
          return Column([
               self.priority_dropdown,
               self.color_dropdown,
               self.title_input,
               self.content_input,
               Row([
                    ElevatedButton(
                         "Выбрать дату напоминания",
                         on_click=lambda _: self.page.open(self.reminder_datetime)
                    ),
                    ElevatedButton(
                         "Выбрать время напоминания",
                         on_click=lambda _: self.page.open(self.reminder_time)
                    )
               ]),
               ElevatedButton(
                    "Сохранить заметку",
                    on_click=self.save_note,
                    bgcolor=colors.BLUE_600,
                    color=colors.WHITE
               )
          ], horizontal_alignment='center', spacing=10)

     def create_list_tab(self):
          """
        Создание вкладки списка (заглушка)
        """
          return Container(
               content=Text("Функционал списка будет добавлен позже", size=16),
               alignment=alignment.center
          )

     def save_note(self, e=None):
          """
          Сохранение новой заметки или обновление существующей
          """
          try:
               # Проверка заполненности обязательных полей
               if not self.title_input.value:
                    self.show_notification("Заголовок заметки не может быть пустым")
                    return

               # Подключение к базе данных
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()

               # Текущее время создания
               current_time = datetime.now()

               # Если заметка новая
               if self.current_note_id is None:
                    cursor.execute('''
                      INSERT INTO notes 
                      (title, content, priority, color, created, completed) 
                      VALUES (?, ?, ?, ?, ?, ?)
                  ''', (
                         self.title_input.value,
                         self.content_input.value,
                         self.priority_dropdown.value or "Низкий",
                         self.color_dropdown.value or "Белый",
                         current_time,
                         0
                    ))
                    self.show_notification("Заметка успешно создана")
               else:
                    # Обновление существующей заметки
                    cursor.execute('''
                      UPDATE notes 
                      SET title=?, content=?, priority=?, color=? 
                      WHERE id=?
                  ''', (
                         self.title_input.value,
                         self.content_input.value,
                         self.priority_dropdown.value,
                         self.color_dropdown.value,
                         self.current_note_id
                    ))
                    self.show_notification("Заметка обновлена")

               # Сохранение изменений
               conn.commit()
               conn.close()

               # Закрытие модального окна и обновление списка заметок
               self.note_modal.open = False
               self.load_notes()
               self.page.update()

          except Exception as ex:
               self.show_notification(f"Ошибка при сохранении заметки: {ex}")

     def open_reminder_modal(self, e=None):
          """
          Открытие модального окна для установки напоминания
          """
          try:
               # Проверка, что заметка создана
               if self.current_note_id is None:
                    # Сначала сохраняем заметку
                    self.save_note()
                    if self.current_note_id is None:
                         self.show_notification("Сначала создайте заметку")
                         return

               # Открытие модального окна напоминания
               self.reminder_modal.open = True
               self.page.update()
          except Exception as ex:
               self.show_notification(f"Ошибка при открытии модального окна напоминания: {ex}")

     def save_reminder(self, e=None):
          """
          Сохранение напоминания для заметки
          """
          try:
               # Проверка выбора даты и времени
               if not self.reminder_datetime.value or not self.reminder_time.value:
                    self.show_notification("Выберите дату и время напоминания")
                    return

               # Объединение даты и времени
               reminder_time = datetime.combine(
                    self.reminder_datetime.value,
                    self.reminder_time.value
               )

               # Проверка, что время напоминания в будущем
               if reminder_time <= datetime.now():
                    self.show_notification("Время напоминания должно быть в будущем")
                    return

               # Подключение к базе данных
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()

               # Обновление заметки с временем напоминания
               cursor.execute('''
                  UPDATE notes 
                  SET reminder_time = ? 
                  WHERE id = ?
              ''', (reminder_time, self.current_note_id))

               conn.commit()
               conn.close()

               # Закрытие модальных окон
               self.reminder_modal.open = False
               self.note_modal.open = False

               self.show_notification(f"Напоминание установлено на {reminder_time}")
               self.load_notes()
               self.page.update()

          except Exception as ex:
               self.show_notification(f"Ошибка при сохранении напоминания: {ex}")

     def show_notification(self, message):
          """
          Показ уведомления с использованием современного API
          """
          snack_bar = SnackBar(
               content=Text(message),
               duration=3000  # длительность отображения в миллисекундах
          )
          self.page.overlay.append(snack_bar)
          self.page.update()
          snack_bar.open = True
          self.page.update()

     def load_notes(self):
          """
        Загрузка активных заметок из базы данных
        """
          self.notes_list.controls.clear()

          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               cursor.execute('SELECT * FROM notes WHERE completed = 0 ORDER BY created DESC')
               notes = cursor.fetchall()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка при загрузке заметок: {e}"))
               self.page.snack_bar.open = True
               return
          finally:
               conn.close()

          for note in notes:
               # Форматирование времени напоминания
               if note[7]:  # Если время напоминания существует
                    try:
                         reminder_datetime = datetime.fromisoformat(str(note[7]))
                         reminder_text = f"Напоминание: {reminder_datetime.strftime('%d.%m.%Y %H:%M')}"
                    except (ValueError, TypeError):
                         reminder_text = "Некорректное время напоминания"
               else:
                    reminder_text = "Добавить напоминание"

               note_container = Container(
                    width=850,
                    padding=10,
                    bgcolor=self.color_palette.get(note[4], colors.WHITE70),
                    border_radius=10,
                    content=Column([
                         Text(f"Приоритет: {note[3]}", weight=FontWeight.BOLD),
                         Text(note[1], size=18, weight=FontWeight.W_600),
                         Text(note[2], size=14),
                         Row([
                              Text(f"Создано: {note[5]}", size=10, color=colors.BLACK54),
                              Text(reminder_text, size=10, color=colors.BLACK54),
                              Row([
                                   IconButton(
                                        icon=icons.EDIT,
                                        icon_color=colors.BLUE,
                                        on_click=lambda e, note_data=note: self.edit_note(note_data)
                                   ),
                                   IconButton(
                                        icon=icons.DELETE,
                                        icon_color=colors.RED,
                                        on_click=lambda e, note_id=note[0]: self.delete_note(note_id)
                                   ),
                                   IconButton(
                                        icon=icons.ALARM_ADD,
                                        icon_color=colors.GREEN,
                                        on_click=lambda e, note_id=note[0]: self.open_reminder_modal(note_id)
                                   )
                              ])
                         ])
                    ])
               )
               self.notes_list.controls.append(note_container)

     def edit_note(self, note_data):
          """
        Редактирование заметки
        """
          # Создаем модальное окно для редактирования
          edit_modal = BottomSheet(
               Container(
                    width=600,
                    padding=20,
                    content=Column([
                         Text("Редактирование заметки", size=20, weight=FontWeight.BOLD),

                         # Поле ввода заголовка
                         TextField(
                              label="Заголовок",
                              value=note_data[1],
                              width=600,
                              ref=self.edit_title_input
                         ),

                         # Поле ввода содержимого
                         TextField(
                              label="Содержание",
                              value=note_data[2],
                              multiline=True,
                              min_lines=5,
                              max_lines=10,
                              width=600,
                              ref=self.edit_content_input
                         ),

                         # Выпадающий список приоритетов
                         Dropdown(
                              label="Степень важности",
                              options=[
                                   dropdown.Option("Низкий"),
                                   dropdown.Option("Средний"),
                                   dropdown.Option("Высокий")
                              ],
                              value=note_data[3],
                              width=300,
                              ref=self.edit_priority_dropdown
                         ),

                         # Выпадающий список цветов
                         Dropdown(
                              label="Цвет заметки",
                              options=[dropdown.Option(color) for color in self.color_palette.keys()],
                              value=note_data[4],
                              width=300,
                              ref=self.edit_color_dropdown
                         ),

                         # Кнопка сохранения изменений
                         ElevatedButton(
                              "Сохранить изменения",
                              on_click=self.save_edited_note,
                              bgcolor=colors.BLUE_600,
                              color=colors.WHITE,
                              data=note_data[0]  # Передаем ID заметки
                         )
                    ], horizontal_alignment='center')
               )
          )

          # Открываем модальное окно
          edit_modal.open = True
          self.page.overlay.append(edit_modal)
          self.page.update()

     def save_edited_note(self, e):
          """
        Сохранение отредактированной заметки
        """
          note_id = e.control.data  # Получаем ID заметки

          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               cursor.execute('''
                UPDATE notes 
                SET title = ?, content = ?, priority = ?, color = ?
                WHERE id = ?
            ''', (
                    self.edit_title_input.current.value,
                    self.edit_content_input.current.value,
                    self.edit_priority_dropdown.current.value,
                    self.edit_color_dropdown.current.value,
                    note_id
               ))
               conn.commit()

               # Показываем уведомление об успешном сохранении
               self.page.snack_bar = SnackBar(
                    content=Text("Заметка успешно обновлена"),
                    bgcolor=colors.GREEN
               )
               self.page.snack_bar.open = True

          except sqlite3.Error as e:
               # Показываем уведомление об ошибке
               self.page.snack_bar = SnackBar(
                    content=Text(f"Ошибка при сохранении: {e}"),
                    bgcolor=colors.RED
               )
               self.page.snack_bar.open = True

          finally:
               conn.close()

          # Обновляем список заметок
          self.load_notes()
          self.page.update()

     def delete_note(self, note_id):
          """
        Удаление заметки (перемещение в корзину)
        """
          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               cursor.execute('UPDATE notes SET completed = 1, deleted_at = ? WHERE id = ?',
                              (datetime.now().isoformat(), note_id))
               conn.commit()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка при удалении: {e}"))
               self.page.snack_bar.open = True
          finally:
               conn.close()

          self.load_notes()
          self.page.update()

     def load_trash_notes(self):
          """
        Загрузка заметок из корзины
        """
          # Очистка существующих заметок
          self.notes_list.controls.clear()

          try:
               # Загрузка заметок из корзины
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               cursor.execute('SELECT * FROM notes WHERE completed = 1 ORDER BY deleted_at DESC')
               notes = cursor.fetchall()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка при загрузке корзины: {e}"))
               self.page.snack_bar.open = True
               return
          finally:
               conn.close()

          # Заполнение списка заметок в корзине
          for note in notes:
               note_container = Container(
                    width=850,
                    padding=10,
                    bgcolor=self.color_palette.get(note[4], colors.WHITE70),
                    border_radius=10,
                    content=Column([
                         Text(f"Приоритет: {note[3]}", weight=FontWeight.BOLD),
                         Text(note[1], size=18, weight=FontWeight.W_600),
                         Text(note[2], size=14),
                         Row([
                              Text(f"Удалено: {note[6]}", size=10, color=colors.BLACK54),
                              Row([
                                   IconButton(
                                        icon=icons.RESTORE,
                                        icon_color=colors.GREEN,
                                        on_click=lambda e, note_id=note[0]: self.restore_note(note_id)
                                   ),
                                   IconButton(
                                        icon=icons.DELETE_FOREVER,
                                        icon_color=colors.RED,
                                        on_click=lambda e, note_id=note[0]: self.permanent_delete(note_id)
                                   )
                              ])
                         ])
                    ])
               )
               self.notes_list.controls.append(note_container)

     def restore_note(self, note_id):
          """
        Восстановление заметки из корзины
        """
          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               cursor.execute('UPDATE notes SET completed = 0, deleted_at = NULL WHERE id = ?', (note_id,))
               conn.commit()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка при восстановлении: {e}"))
               self.page.snack_bar.open = True
          finally:
               conn.close()

          self.load_trash_notes()
          self.page.update()

     def permanent_delete(self, note_id):
          """
        Окончательное удаление заметки
        """
          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))
               conn.commit()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка при удалении: {e}"))
               self.page.snack_bar.open = True
          finally:
               conn.close()

          self.load_trash_notes()
          self.page.update()

     def cleanup_old_notes(self):
          """
        Удаление заметок старше 7 дней в корзине
        """
          try:
               conn = sqlite3.connect('tasks.db')
               cursor = conn.cursor()
               seven_days_ago = datetime.now() - timedelta(days=7)
               cursor.execute('DELETE FROM notes WHERE completed = 1 AND deleted_at < ?', (seven_days_ago,))
               conn.commit()
          except sqlite3.Error as e:
               self.page.snack_bar = SnackBar(content=Text(f"Ошибка при очистке корзины: {e}"))
               self.page.snack_bar.open = True
          finally:
               conn.close()


def main(page: Page):
     """
    Основная функция приложения
    Настройка интерфейса и логики
    """
     try:
          print("Начало инициализации приложения")  # Отладочное сообщение

          # Инициализация базы данных
          init_db()
          print("База данных инициализирована")  # Отладочное сообщение

          # Настройка страницы
          page.title = "MyNote"
          page.window.width = 1225
          page.window.height = 940
          page.window.resizable = False
          page.theme_mode = ThemeMode.DARK
          page.padding = 0
          page.window.icon = 'Frame 5.png'

          # Создание экземпляров менеджеров
          notes_instance = Notes(page)
          list_manager = ListManager(page)  # Добавляем менеджер списков
          print("Экземпляры менеджеров созданы")  # Отладочное сообщение

          notes_instance.reminder_manager.start_reminder_check()
          print("Проверка напоминаний запущена")  # Отладочное сообщение

          def open_tg(page):
               page.launch_url("https://t.me/thefirstWebbApppbot")

          def open_site(page):
               page.launch_url("https://project11975037.tilda.ws/")

          def get_notes_count():
               """Получение количества заметок"""
               try:
                    conn = sqlite3.connect('tasks.db')
                    cursor = conn.cursor()

                    # Общее количество заметок
                    cursor.execute('SELECT COUNT(*) FROM notes WHERE completed = 0')
                    total_notes = cursor.fetchone()[0]

                    # Количество заметок в корзине
                    cursor.execute('SELECT COUNT(*) FROM notes WHERE completed = 1')
                    trash_notes = cursor.fetchone()[0]

                    # Количество активных напоминаний
                    cursor.execute('SELECT COUNT(*) FROM notes WHERE completed = 0 AND reminder_time IS NOT NULL')
                    active_reminders = cursor.fetchone()[0]

                    # Количество списков
                    cursor.execute('SELECT COUNT(*) FROM lists')
                    total_lists = cursor.fetchone()[0]

                    conn.close()

                    return total_notes, trash_notes, active_reminders, total_lists
               except Exception as e:
                    print(f"Ошибка при подсчете заметок: {e}")
                    return 0, 0, 0, 0

          # Контейнер для списков с новой функциональностью
          _lists = Container(
               width=900,
               height=950,
               bgcolor=colors.BLACK12,
               content=Column(
                    horizontal_alignment='center',
                    controls=[
                         Text('Мои списки', size=25, color=colors.WHITE),
                         notes_instance.search_input,
                         notes_instance.priority_filter,
                         notes_instance.color_filter,
                         Container(
                              height=750,
                              content=list_manager.list_items_container
                         ),
                         Container(
                              on_click=lambda e: page.open(list_modal),  # Открытие модального окна для списков
                              bgcolor=colors.BLUE_600,
                              height=50,
                              width=850,
                              border_radius=15,
                              alignment=alignment.center,
                              content=Text("Добавить список", color=colors.WHITE, text_align='center')
                         )
                    ]
               )
          )

          # Модальное окно для создания списков
          list_modal = BottomSheet(
               Container(
                    width=800,
                    height=700,
                    padding=20,
                    content=Column(
                         [
                              Tabs(
                                   selected_index=0,
                                   width=760,
                                   tabs=[
                                        Tab(
                                             text="Заметка",
                                             content=Container(
                                                  content=Column(
                                                       [notes_instance.create_note_tab()],
                                                       scroll='auto',
                                                       height=600
                                                  )
                                             )
                                        ),
                                        Tab(
                                             text="Список",
                                             content=Container(
                                                  content=Column(
                                                       [list_manager.create_list_tab()],
                                                       scroll='auto',
                                                       height=600
                                                  )
                                             )
                                        )
                                   ]
                              )
                         ],
                         horizontal_alignment='center',
                         scroll='auto'
                    )
               )
          )

          # Контейнер Главная страница (без изменений)
          _home = Container(
               width=880,
               height=900,
               margin=margin.only(top=15),
               content=Column(
                    horizontal_alignment='center',
                    controls=[
                         Text('Добро пожаловать в MyNote!', size=25, color=colors.WHITE),
                         Text('Создавайте, организуйте и управляйте своими заметками', size=16, color=colors.WHITE54),

                         # Контейнер с информацией о функциях
                         Container(
                              width=800,
                              padding=20,
                              bgcolor=colors.WHITE10,
                              border_radius=10,
                              content=Column([
                                   Text('Возможности приложения:', size=20, weight=FontWeight.BOLD),
                                   Text('• Создание заметок с настройкой приоритета', size=16),
                                   Text('• Цветовая кодировка заметок', size=16),
                                   Text('• Система напоминаний', size=16),
                                   Text('• Поиск и фильтрация заметок', size=16),
                                   Text('• Корзина с восстановлением', size=16)
                              ])
                         ),

                         Container(
                              margin=margin.only(top=250, left=15),
                              content=Column(
                                   [
                                        Divider(),
                                        Row(
                                             [
                                                  Container(
                                                       margin=margin.only(left=20),
                                                       content=Column(
                                                            controls=[
                                                                 Container(
                                                                      margin=margin.only(left=15),
                                                                      content=Text(
                                                                           'Техническая поддержка',
                                                                           size=24),
                                                                 ),
                                                                 Text('Телеграм бот тех.поддержки:',
                                                                      size=15),
                                                                 ElevatedButton(
                                                                      "Открыть телеграм",
                                                                      on_click=lambda e: open_tg(page),
                                                                      width=200
                                                                 ),
                                                            ]
                                                       ),
                                                  ),
                                                  Container(
                                                       margin=margin.only(left=180),
                                                       content=Column(
                                                            controls=[
                                                                 Container(
                                                                      margin=margin.only(left=25),
                                                                      content=Text('О нашем приложении:',
                                                                                   size=24),
                                                                 ),
                                                                 Text('сайт-визитка:',
                                                                      size=15),
                                                                 ElevatedButton(
                                                                      "Перейти на сайт",
                                                                      on_click=lambda e: open_site(page),
                                                                      width=200
                                                                 )
                                                            ]
                                                       )
                                                  )
                                             ]
                                        )
                                   ]
                              )
                         )
                    ]
               )
          )

          # Контейнер Мои заметки (без изменений)
          _mynotes = Container(
               width=900,
               height=950,
               bgcolor=colors.BLACK12,
               content=Column(
                    horizontal_alignment='center',
                    controls=[
                         Text('Мои заметки', size=25, color=colors.WHITE),
                         notes_instance.create_search_container(),
                         Container(
                              height=600,
                              content=Column(
                                   scroll='auto',
                                   controls=[
                                        notes_instance.notes_list
                                   ]
                              )
                         ),
                         Container(
                              on_click=lambda e: notes_instance.open_note_modal(e),
                              bgcolor=colors.BLUE_600,
                              height=50,
                              width=850,
                              border_radius=15,
                              alignment=alignment.center,
                              content=Text("Добавить заметку", color=colors.WHITE, text_align='center')
                         )
                    ]
               )
          )

          # Контейнер "Корзина" (без изменений)
          _rubbish = Container(
               width=900,
               height=900,
               bgcolor=colors.BLACK12,
               content=Column(
                    horizontal_alignment='center',
                    controls=[
                         Text('Корзина', size=25, color=colors.WHITE),
                         Container(
                              height=750,
                              content=Column(
                                   scroll='auto',
                                   controls=[
                                        notes_instance.notes_list
                                   ]
                              )
                         ),
                         Container(
                              content=Text(
                                   "Заметки в корзине автоматически удаляются через 7 дней",
                                   color=colors.WHITE54,
                                   text_align='center'
                              ),
                              padding=10
                         )
                    ]
               )
          )

          # Обновленный контейнер "Аккаунт" с информацией о списках
          total_notes, trash_notes, active_reminders, total_lists = get_notes_count()
          _account = Container(
               width=900,
               height=900,
               bgcolor=colors.BLACK12,
               content=Column(
                    horizontal_alignment='center',
                    controls=[
                         Text('Ваш аккаунт', size=25, color=colors.WHITE),
                         Container(
                              width=800,
                              padding=20,
                              bgcolor=colors.WHITE10,
                              border_radius=10,
                              content=Column([
                                   Text('Статистика:', size=20, weight=FontWeight.BOLD),
                                   Text(f'Всего заметок: {total_notes}', size=16),
                                   Text(f'Заметок в корзине: {trash_notes}', size=16),
                                   Text(f'Активных напоминаний: {active_reminders}', size=16),
                                   Text(f'Всего списков: {total_lists}', size=16)
                              ])
                         )
                    ]
               )
          )

          # Контейнер для правой части содержимого
          right_content = Container(
               width=900,
               height=900,
               bgcolor=colors.BLACK12,
               content=_home
          )

          # Функция для обновления правой части содержимого
          def change_content(e):
               try:
                    if e.control.text == 'Дом':
                         right_content.content = _home
                    elif e.control.text == 'Мои заметки':
                         right_content.content = _mynotes
                         notes_instance.load_notes()
                    elif e.control.text == 'Корзина':
                         right_content.content = _rubbish
                         notes_instance.load_trash_notes()
                         notes_instance.cleanup_old_notes()
                    elif e.control.text == 'Списки':
                         right_content.content = _lists
                         list_manager.load_lists()  # Загрузка списков
                    elif e.control.text == 'Аккаунт':
                         # Обновляем статистику при открытии
                         total_notes, trash_notes, active_reminders, total_lists = get_notes_count()
                         _account.content.controls[1].content.controls[1].value = f'Всего заметок: {total_notes}'
                         _account.content.controls[1].content.controls[2].value = f'Заметок в корзине: {trash_notes}'
                         _account.content.controls[1].content.controls[
                              3].value = f'Активных напоминаний: {active_reminders}'
                         _account.content.controls[1].content.controls[4].value = f'Всего списков: {total_lists}'
                         right_content.content = _account

                    page.update()
               except Exception as e:
                    snack_bar = SnackBar(
                         content=Text(f"Ошибка при смене контента: {e}"),
                         duration=3000
                    )
                    page.overlay.append(snack_bar)
                    page.update()
                    snack_bar.open = True
                    page.update()

          # Главный контейнер
          _c = Container(
               height=900,
               width=1200,
               content=Row(
                    controls=[
                         Container(
                              alignment=alignment.center_left,
                              height=900,
                              width=300,
                              bgcolor=colors.WHITE12,
                              content=Column(
                                   horizontal_alignment='center',
                                   controls=[
                                        Container(
                                             margin=margin.only(top=10, left=30, bottom=45),
                                             content=Row(
                                                  [Image(src='Frame 5.png'),
                                                   Text('MyNote', color=colors.WHITE, size=20)])
                                        ),
                                        Container(
                                             margin=margin.only(top=10, left=20),
                                             content=CupertinoFilledButton(
                                                  text='Дом',
                                                  icon=icons.HOME,
                                                  width=250,
                                                  height=50,
                                                  padding=padding.only(right=40),
                                                  on_click=change_content
                                             )
                                        ),
                                        Container(
                                             margin=margin.only(top=5, left=20),
                                             content=CupertinoFilledButton(
                                                  text='Мои заметки',
                                                  icon=icons.NOTE,
                                                  width=250,
                                                  height=50,
                                                  padding=padding.only(right=40),
                                                  on_click=change_content
                                             )
                                        ),
                                        Container(
                                             margin=margin.only(top=5, left=20),
                                             content=CupertinoFilledButton(
                                                  text='Списки',
                                                  icon=icons.LIST,
                                                  width=250,
                                                  height=50,
                                                  padding=padding.only(right=40),
                                                  on_click=change_content
                                             )
                                        ),
                                        Container(
                                             margin=margin.only(top=5, left=20),
                                             content=CupertinoFilledButton(
                                                  text='Корзина',
                                                  icon=icons.DELETE,
                                                  width=250,
                                                  height=50,
                                                  padding=padding.only(right=40),
                                                  on_click=change_content
                                             )
                                        ),
                                        Container(
                                             margin=margin.only(top=5, left=20),
                                             content=CupertinoFilledButton(
                                                  text='Аккаунт',
                                                  icon=icons.ACCOUNT_CIRCLE,
                                                  width=250,
                                                  height=50,
                                                  padding=padding.only(right=40),
                                                  on_click=change_content
                                             )
                                        )
                                   ]
                              )
                         ),
                         right_content
                    ]
               )
          )

          # Добавление главного контейнера на страницу
          page.add(_c)

          # Добавляем модальное окно в overlay
          page.overlay.append(list_modal)

          # ВАЖНО: Загрузка начальных заметок
          notes_instance.load_notes()

     except Exception as ex:
          snack_bar = SnackBar(content=Text(f"Критическая ошибка: {ex}"))
          page.overlay.append(snack_bar)
          page.update()
          snack_bar.open = True
          page.update()


if __name__ == "__main__":
     app(target=main)

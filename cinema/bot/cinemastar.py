import telebot
from config import BOT_TOKEN
import telebot.types as types

from sqlalchemy import Column, Integer, String, create_engine, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship



Base = declarative_base()

class Cinema(Base):
    __tablename__ = 'cinemas'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    address = Column(String)

class Movie(Base):
    __tablename__ = 'movies'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    description = Column(String, nullable=True)

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey('movies.id'))
    cinema_id = Column(Integer, ForeignKey('cinemas.id'))
    date = Column(String)  # Формат: 'YYYY-MM-DD'
    time = Column(String)  # Формат: 'HH:MM'
    movie = relationship("Movie")
    cinema = relationship("Cinema")

class Seat(Base):
    __tablename__ = 'seats'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'))
    row = Column(Integer)  # Ряд (1-9)
    number = Column(Integer)  # Место (1-13)
    is_booked = Column(Boolean, default=False)
    session = relationship("Session")

# Инициализация БД
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:postgres@db:5432/postgres"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()


user_data = {}
bot = telebot.TeleBot(BOT_TOKEN)

def init_db():
    # Очистка старых данных (опционально)
    db.query(Cinema).delete()
    db.query(Movie).delete()
    db.query(Session).delete()
    db.query(Seat).delete()

    # Добавляем кинотеатры
    cinemas = [
        Cinema(name="Киномакс", address="ул. Пушкина, 10"),
        Cinema(name="Синема Парк", address="ул. Ленина, 5")
    ]
    db.add_all(cinemas)
    db.commit()

    # Добавляем фильмы
    movies = [
        Movie(title="Дюна", description="Фантастика"),
        Movie(title="Крепкий орешек", description="Боевик")
    ]
    db.add_all(movies)
    db.commit()

    # Добавляем сеансы
    sessions = [
        Session(movie_id=1, cinema_id=1, date="2024-12-20", time="18:00"),
        Session(movie_id=2, cinema_id=2, date="2024-12-21", time="20:00")
    ]
    db.add_all(sessions)
    db.commit()

    # Добавляем места (9 рядов × 13 мест)
    for session in sessions:
        for row in range(1, 10):
            for seat_num in range(1, 14):
                db.add(Seat(
                    session_id=session.id,
                    row=row,
                    number=seat_num,
                    is_booked=False  # Пока все места свободны
                ))
    db.commit()


@bot.message_handler(commands=['start'])
def start(message):
    user_data[message.chat.id] = {}  # Создаем запись для пользователя
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    cinemas = db.query(Cinema).all()
    for cinema in cinemas:
        markup.add(types.KeyboardButton(cinema.address))
    bot.send_message(
        message.chat.id,
        "🎬 Выберите кинотеатр:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text in [c.address for c in db.query(Cinema).all()])
def select_cinema(message):
    cinema = db.query(Cinema).filter_by(address=message.text).first()
    user_data[message.chat.id]['cinema_id'] = cinema.id

    # Получаем фильмы в этом кинотеатре
    sessions = db.query(Session).filter_by(cinema_id=cinema.id).all()
    movies = {s.movie for s in sessions}

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for movie in movies:
        markup.add(types.KeyboardButton(movie.title))
    
    bot.send_message(
        message.chat.id,
        "📽 Выберите фильм:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text in [mov.title for mov in db.query(Movie).all()])
def select_movie(message):
    movie = db.query(Movie).filter_by(title=message.text).first()
    user_data[message.chat.id]['movie_id'] = movie.id

    # Получаем сеансы для этого фильма в выбранном кинотеатре
    sessions = db.query(Session).filter_by(
        cinema_id=user_data[message.chat.id]['cinema_id'],
        movie_id=movie.id
    ).all()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for session in sessions:
        btn_text = f"{session.date} {session.time}"
        markup.add(types.KeyboardButton(btn_text))
    
    bot.send_message(
        message.chat.id,
        "📅 Выберите дату и время сеанса:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: any(f"{s.date} {s.time}" == m.text for s in db.query(Session).all()))
def select_session(message):
    date, time = message.text.split()
    session = db.query(Session).filter_by(date=date, time=time).first()
    user_data[message.chat.id]['session_id'] = session.id

    seats = db.query(Seat).filter_by(session_id=session.id).order_by(Seat.number, Seat.row).all()
    
    # Создаем клавиатуру
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=9)
    
    # Добавляем обозначение экрана слева
    screen_row = ["🎦 ЭКРАН"] + [""]*8  # Первая кнопка в ряду - обозначение экрана
    markup.row(*screen_row)
    
    # Создаем 13 рядов по 9 мест (учитываем, что первая кнопка в ряду - номер ряда)
    for row_num in range(1, 14):
        row_buttons = [f"Ряд {row_num}"]  # Первая кнопка в ряду - номер ряда
        
        for seat_num in range(1, 10):
            seat = next((s for s in seats if s.row == row_num and s.number == seat_num), None)
            if seat and seat.is_booked:
                row_buttons.append("❌")
            else:
                row_buttons.append("🟢")
        
        markup.row(*row_buttons)
    
    # Добавляем пояснение и кнопку отмены
    markup.row(types.KeyboardButton("🟢 - свободно | ❌ - занято"))
    markup.row(types.KeyboardButton("Отменить выбор"))
    
    bot.send_message(
        message.chat.id,
        "Выберите место (экран слева):",
        reply_markup=markup
    )

selected_seats = {}

@bot.message_handler(func=lambda m: m.text.strip() in ["🟢", "❌"])
def handle_seat_selection(message):
    chat_id = message.chat.id
    
    # Проверяем, что пользователь уже выбрал сеанс
    if chat_id not in user_data or 'session_id' not in user_data[chat_id]:
        bot.send_message(chat_id, "Сначала выберите сеанс!")
        return
    
    # Получаем информацию о ряде из предыдущего сообщения
    reply_markup = message.reply_markup
    if not reply_markup:
        bot.send_message(chat_id, "Ошибка определения места. Попробуйте снова.")
        return
    
    # Ищем в какой строке была нажата кнопка
    for row in reply_markup.keyboard:
        if message.text in row:
            row_index = reply_markup.keyboard.index(row)
            seat_index = row.index(message.text)
            break
    else:
        bot.send_message(chat_id, "Не удалось определить место.")
        return
    
    # Если место занято
    if message.text == "❌":
        bot.send_message(chat_id, "Это место уже занято! Выберите другое.")
        return
    
    # Определяем ряд и место
    seat_row = row_index  # Ряды нумеруются с 1 (после строки с экраном)
    seat_number = seat_index
    
    # Проверяем свободно ли место в БД
    session_id = user_data[chat_id]['session_id']
    seat = db.query(Seat).filter_by(
        session_id=session_id,
        row=seat_row,
        number=seat_number
    ).first()
    
    if not seat or seat.is_booked:
        bot.send_message(chat_id, "Место уже забронировано! Обновите схему мест.")
        return
    
    # Сохраняем выбранное место во временное хранилище
    selected_seats[chat_id] = {
        'seat_id': seat.id,
        'row': seat_row,
        'number': seat_number
    }
    
    # Создаем клавиатуру подтверждения
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("✅ Подтвердить бронь"))
    markup.row(types.KeyboardButton("❌ Отменить выбор"))
    
    bot.send_message(
        chat_id,
        f"Вы выбрали: Ряд {seat_row}, Место {seat_number}\n"
        f"Подтвердите бронирование:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "✅ Подтвердить бронь")
def confirm_booking(message):
    chat_id = message.chat.id
    
    if chat_id not in selected_seats:
        bot.send_message(chat_id, "Не найдено выбранное место.")
        return
    
    seat_data = selected_seats[chat_id]
    
    # Обновляем место в БД
    seat = db.query(Seat).get(seat_data['seat_id'])
    if seat.is_booked:
        bot.send_message(chat_id, "К сожалению, место уже забронировано.")
        return
    
    seat.is_booked = True

    db.commit()
    
    # Отправляем подтверждение
    session = db.query(Session).get(user_data[chat_id]['session_id'])
    cinema = db.query(Cinema).get(session.cinema_id)
    movie = db.query(Movie).get(session.movie_id)
    
    bot.send_message(
        chat_id,
        f"✅ Бронирование подтверждено!\n\n"
        f"🎬 Фильм: {movie.title}\n"
        f"🏠 Кинотеатр: {cinema.name}\n"
        f"📅 Дата: {session.date} {session.time}\n"
        f"💺 Место: Ряд {seat_data['row']}, Место {seat_data['number']}\n\n"
        f"Приятного просмотра!",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    # Очищаем временные данные
    del selected_seats[chat_id]
    if chat_id in user_data:
        del user_data[chat_id]

@bot.message_handler(func=lambda m: m.text == "❌ Отменить выбор")
def cancel_booking(message):
    chat_id = message.chat.id
    if chat_id in selected_seats:
        del selected_seats[chat_id]
    
    bot.send_message(
        chat_id,
        "Вы отменили выбор места.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    # Можно снова показать схему мест
    select_session(message)


if __name__ == "__main__":
    init_db()
    print("Бот запущен!")
    bot.infinity_polling()
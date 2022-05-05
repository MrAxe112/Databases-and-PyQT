import os

import sqlalchemy as db
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime


class ClientStorage:
    """ Класс для работы с базой данных клиента. Используется SQLAlchemy ORM с SQLite базой данныхю
    Для работы выбран декларативный подход.
    """
    Base = declarative_base()

    class KnownUsers(Base):
        """ Класс для создания таблиц всех известных пользвателей."""
        __tablename__ = 'Known_users'
        id = db.Column('id', db.Integer, primary_key=True)
        username = db.Column('username', db.String)

        def __init__(self, user):
            self.username = user
            self.id = None

    class MessageHistory(Base):
        """ Класс для создания таблиц ведения учета сообщений пользователя."""
        __tablename__ = 'Message_history'
        id = db.Column('id', db.Integer, primary_key=True)
        from_user = db.Column('from_user', db.String)
        to_user = db.Column('to_user', db.String)
        message = db.Column('message', db.Text)
        date = db.Column('date', db.DateTime)

        def __init__(self, from_user, to_user, message):
            self.from_user = from_user
            self.to_user = to_user
            self.message = message
            self.date = datetime.datetime.now()
            self.id = None

    class Contacts(Base):
        """ Класс для создания таблиц ведения учета контактов пользователя."""
        __tablename__ = 'Contacts'
        id = db.Column('id', db.Integer, primary_key=True)
        name = db.Column('name', db.String, unique=True)

        def __init__(self, contact):
            self.name = contact
            self.id = None

    def __init__(self, client_name):
        path = os.path.dirname(os.path.realpath(__file__))
        filename = f'client_{client_name}.db3'
        self.database_engine = db.create_engine(f'sqlite:///{os.path.join(path, filename)}',
                                                echo=False, pool_recycle=7200,
                                                connect_args={'check_same_thread': False})
        self.Base.metadata.create_all(self.database_engine)

        Session = sessionmaker(bind=self.database_engine)
        self.session = Session()
        self.session.query(self.Contacts).delete()
        self.session.commit()

    def add_contact(self, contact):
        """Метод добавления пользователя в список контактов """
        if not self.session.query(self.Contacts).filter_by(name=contact).count():
            contact_row = self.Contacts(contact)
            self.session.add(contact_row)
            self.session.commit()

    def del_contact(self, contact):
        """Метод удаления пользователя из списока контактов """
        self.session.query(self.Contacts).filter_by(name=contact).delete()
        self.session.commit()

    def add_users(self, users_list):
        """Метод обновления списка пользователей"""
        self.session.query(self.KnownUsers).delete()
        for user in users_list:
            user_row = self.KnownUsers(user)
            self.session.add(user_row)
        self.session.commit()

    def save_message(self, from_user, to_user, message):
        """Метод сохранения сообщения пользователя."""
        message_row = self.MessageHistory(from_user, to_user, message)
        self.session.add(message_row)
        self.session.commit()

    def get_contacts(self):
        """Метод списка контактов пользователя."""

        return [contact[0] for contact in self.session.query(self.Contacts.name).all()]

    def get_users(self):
        """Метод возвращающий список известных пользователей"""
        return [user[0] for user in self.session.query(self.KnownUsers.username).all()]

    def check_user(self, user):
        """Метод проверки наличия пользователя"""
        if self.session.query(self.KnownUsers).filter_by(username=user).count():
            return True
        else:
            return False

    def check_contact(self, contact):
        """Метод проверки наличия контакта"""
        if self.session.query(self.Contacts).filter_by(name=contact).count():
            return True
        else:
            return False

    def get_history(self, from_user=None, to_user=None):
        """Метод получения истории сообщений. Возможен отбор по пользователю."""
        query = self.session.query(self.MessageHistory)
        if from_user:
            query = query.filter_by(from_user=from_user)
        if to_user:
            query = query.filter_by(to_user=to_user)
        return [(history_row.from_user, history_row.to_user, history_row.message, history_row.date)
                for history_row in query.all()]

# Начать реализацию класса «Хранилище» для серверной стороны. Хранение необходимо осуществлять в базе данных.
# В качестве СУБД использовать sqlite. Для взаимодействия с БД можно применять ORM.

# Опорная схема базы данных:
# На стороне сервера БД содержит следующие таблицы:

# a) клиент:
# * логин;
# * информация.

# b) история клиента:
# * время входа;
# * ip-адрес.

# c) список активных пользователей (составляется на основании выборки всех записей с id владельца):
# * id_владельца;
# * id_клиента.

import sqlalchemy as db
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime


class ServerStorage:
    Base = declarative_base()

    class Users(Base):
        __tablename__ = 'Users'
        id = db.Column('id', db.Integer, primary_key=True)
        name = db.Column('name', db.String, unique=True)
        last_login = db.Column('last_login', db.DateTime)

        def __init__(self, username):
            self.name = username
            self.last_login = datetime.datetime.now()
            self.id = None

    class ActiveUsers(Base):
        __tablename__ = 'Active_Users'
        id = db.Column('id', db.Integer, primary_key=True)
        user = db.Column('user', db.ForeignKey('Users.id'), unique=True)
        ip_address = db.Column('ip_address', db.String)
        port = db.Column('port', db.Integer)
        login_time = db.Column('login_time', db.DateTime)

        def __init__(self, user_id, ip_address, port, login_time):
            self.user = user_id
            self.ip_address = ip_address
            self.port = port
            self.login_time = login_time
            self.id = None

    class LoginHistory(Base):
        __tablename__ = 'Login_history'
        id = db.Column('id', db.Integer, primary_key=True)
        name = db.Column('name', db.ForeignKey('Users.id'))
        date_time = db.Column('date_time', db.DateTime)
        ip = db.Column('ip', db.String)
        port = db.Column('port', db.String)

        def __init__(self, name, date, ip, port):
            self.id = None
            self.name = name
            self.date_time = date
            self.ip = ip
            self.port = port

    def __init__(self):
        self.database_engine = db.create_engine('sqlite:///server_db.db3', echo=False, pool_recycle=7200)
        self.Base.metadata.create_all(self.database_engine)

        Session = sessionmaker(bind=self.database_engine)
        self.session = Session()
        self.session.query(self.ActiveUsers).delete()
        self.session.commit()

    def user_login(self, username, ip_address, port):
        print(username, ip_address, port)
        rez = self.session.query(self.Users).filter_by(name=username)

        if rez.count():
            user = rez.first()
            user.last_login = datetime.datetime.now()
        else:
            user = self.Users(username)
            self.session.add(user)
            self.session.commit()

        new_active_user = self.ActiveUsers(user.id, ip_address, port, datetime.datetime.now())
        self.session.add(new_active_user)

        history = self.LoginHistory(user.id, datetime.datetime.now(), ip_address, port)
        self.session.add(history)
        self.session.commit()

    def user_logout(self, username):
        user = self.session.query(self.Users).filter_by(name=username).first()

        self.session.query(self.ActiveUsers).filter_by(user=user.id).delete()
        self.session.commit()

    def users_list(self):
        query = self.session.query(
            self.Users.name,
            self.Users.last_login
        )
        return query.all()

    def active_users_list(self):
        query = self.session.query(
            self.Users.name,
            self.ActiveUsers.ip_address,
            self.ActiveUsers.port,
            self.ActiveUsers.login_time
        ).join(self.Users)
        return query.all()

    def login_history(self, username=None):
        query = self.session.query(self.Users.name,
                                   self.LoginHistory.date_time,
                                   self.LoginHistory.ip,
                                   self.LoginHistory.port
                                   ).join(self.Users)
        if username:
            query = query.filter(self.Users.name == username)
        return query.all()


if __name__ == '__main__':
    test_db = ServerStorage()

    test_db.user_login('client_1', '192.168.1.4', 8080)
    test_db.user_login('client_2', '192.168.1.5', 7777)

    print(test_db.active_users_list())
    test_db.user_logout('client_1')
    print(test_db.active_users_list())
    print(test_db.login_history('client_2'))
    print(test_db.users_list())

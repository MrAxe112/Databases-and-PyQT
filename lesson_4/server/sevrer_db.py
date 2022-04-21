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

    class UsersContacts(Base):
        __tablename__ = 'Users_contacts'
        id = db.Column('id', db.Integer, primary_key=True)
        user = db.Column('user', db.ForeignKey('Users.id'))
        contact = db.Column('contact', db.ForeignKey('Users.id'))

        def __init__(self, user, contact):
            self.id = None
            self.user = user
            self.contact = contact

    class UsersHistory(Base):
        __tablename__ = 'Users_history'
        id = db.Column('id', db.Integer, primary_key=True)
        user = db.Column('user', db.ForeignKey('Users.id'))
        sent = db.Column('sent', db.Integer)
        accepted = db.Column('accepted', db.Integer)

        def __init__(self, user):
            self.id = None
            self.user = user
            self.sent = 0
            self.accepted = 0

    def __init__(self, filename):
        self.database_engine = db.create_engine(f'sqlite:///{filename}', echo=False, pool_recycle=7200,
                                                connect_args={'check_same_thread': False})
        self.Base.metadata.create_all(self.database_engine)

        Session = sessionmaker(bind=self.database_engine)
        self.session = Session()
        self.session.query(self.ActiveUsers).delete()
        self.session.commit()

    def user_login(self, username, ip_address, port):
        rez = self.session.query(self.Users).filter_by(name=username)

        if rez.count():
            user = rez.first()
            user.last_login = datetime.datetime.now()
        else:
            user = self.Users(username)
            self.session.add(user)
            self.session.commit()
            user_in_history = self.UsersHistory(user.id)
            self.session.add(user_in_history)

        new_active_user = self.ActiveUsers(user.id, ip_address, port, datetime.datetime.now())
        self.session.add(new_active_user)

        history = self.LoginHistory(user.id, datetime.datetime.now(), ip_address, port)
        self.session.add(history)

        self.session.commit()

    def user_logout(self, username):
        user = self.session.query(self.Users).filter_by(name=username).first()
        self.session.query(self.ActiveUsers).filter_by(user=user.id).delete()

        self.session.commit()

    def process_message(self, sender, recipient):
        sender = self.session.query(self.Users).filter_by(name=sender).first().id
        recipient = self.session.query(self.Users).filter_by(name=recipient).first().id
        sender_row = self.session.query(self.UsersHistory).filter_by(user=sender).first()
        sender_row.sent += 1
        recipient_row = self.session.query(self.UsersHistory).filter_by(user=recipient).first()
        recipient_row.accepted += 1

        self.session.commit()

    def add_contact(self, user, contact):
        user = self.session.query(self.Users).filter_by(name=user).first()
        contact = self.session.query(self.Users).filter_by(name=contact).first()

        if not contact or self.session.query(self.UsersContacts).filter_by(user=user.id, contact=contact.id).count():
            return

        contact_row = self.UsersContacts(user.id, contact.id)
        self.session.add(contact_row)
        self.session.commit()

    def remove_contact(self, user, contact):
        user = self.session.query(self.Users).filter_by(name=user).first()
        contact = self.session.query(self.Users).filter_by(name=contact).first()

        if not contact:
            return

        print(self.session.query(self.UsersContacts).filter(
            self.UsersContacts.user == user.id,
            self.UsersContacts.contact == contact.id
        ).delete())
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

    def get_contacts(self, username):
        user = self.session.query(self.Users).filter_by(name=username).one()
        query = self.session.query(self.UsersContacts, self.Users.name). \
            filter_by(user=user.id). \
            join(self.Users, self.UsersContacts.contact == self.Users.id)

        return [contact[1] for contact in query.all()]

    def message_history(self):
        query = self.session.query(
            self.Users.name,
            self.Users.last_login,
            self.UsersHistory.sent,
            self.UsersHistory.accepted
        ).join(self.Users)
        return query.all()


if __name__ == '__main__':
    test_db = ServerStorage('server_test_db.db3')
    test_db.user_login('user1', '192.168.1.113', 8080)
    test_db.user_login('user2', '192.168.1.113', 8081)
    print(test_db.users_list())
    print(test_db.active_users_list())
    test_db.user_logout('user2')
    print(test_db.login_history('re'))
    test_db.add_contact('test2', 'test1')
    test_db.add_contact('test1', 'test3')
    test_db.add_contact('test1', 'test6')
    test_db.remove_contact('test1', 'test3')
    test_db.process_message('user2', '1111')
    print(test_db.message_history())

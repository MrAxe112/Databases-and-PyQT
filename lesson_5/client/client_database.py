import sqlalchemy as db
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime


class ClientStorage:
    Base = declarative_base()

    class KnownUsers(Base):
        __tablename__ = 'Known_users'
        id = db.Column('id', db.Integer, primary_key=True)
        username = db.Column('username', db.String)

        def __init__(self, user):
            self.username = user
            self.id = None

    class MessageHistory(Base):
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
        __tablename__ = 'Contacts'
        id = db.Column('id', db.Integer, primary_key=True)
        name = db.Column('name', db.String, unique=True)

        def __init__(self, contact):
            self.name = contact
            self.id = None

    def __init__(self, client_name):
        self.database_engine = db.create_engine(f'sqlite:///client_{client_name}.db3', echo=False, pool_recycle=7200,
                                                connect_args={'check_same_thread': False})
        self.Base.metadata.create_all(self.database_engine)

        Session = sessionmaker(bind=self.database_engine)
        self.session = Session()
        self.session.query(self.Contacts).delete()
        self.session.commit()

    def add_contact(self, contact):
        if not self.session.query(self.Contacts).filter_by(name=contact).count():
            contact_row = self.Contacts(contact)
            self.session.add(contact_row)
            self.session.commit()

    def del_contact(self, contact):
        self.session.query(self.Contacts).filter_by(name=contact).delete()
        self.session.commit()

    def add_users(self, users_list):
        self.session.query(self.KnownUsers).delete()
        for user in users_list:
            user_row = self.KnownUsers(user)
            self.session.add(user_row)
        self.session.commit()

    def save_message(self, from_user, to_user, message):
        message_row = self.MessageHistory(from_user, to_user, message)
        self.session.add(message_row)
        self.session.commit()

    def get_contacts(self):
        return [contact[0] for contact in self.session.query(self.Contacts.name).all()]

    def get_users(self):
        return [user[0] for user in self.session.query(self.KnownUsers.username).all()]

    def check_user(self, user):
        if self.session.query(self.KnownUsers).filter_by(username=user).count():
            return True
        else:
            return False

    def check_contact(self, contact):
        if self.session.query(self.Contacts).filter_by(name=contact).count():
            return True
        else:
            return False

    def get_history(self, from_who=None, to_who=None):
        query = self.session.query(self.MessageHistory)
        if from_who:
            query = query.filter_by(from_user=from_who)
        if to_who:
            query = query.filter_by(to_user=to_who)
        return [(history_row.from_user, history_row.to_user, history_row.message, history_row.date)
                for history_row in query.all()]

import irc.bot
import sys
import psycopg2
# from DataResponse import extracted_chat
from EntGen import extracted_chat


# Track number,e1.category, e1.trackId, e12.callsign

# Database connection
print("Script running...")


def get_db_connection():
    conn = psycopg2.connect(
        host="10.5.185.53",
        dbname="shooca_db",
        user="shooca",
        password="shooca222",
        port="5432"
    )
    return conn

# Function to insert message into PostgreSQL
def insert_message(message, entity, action1, action2, action3):
    try: 
        print("Begin inserting message")
        conn = get_db_connection()
        cur = conn.cursor()
        # cur.execute("INSERT INTO pae_data (message) VALUES (%s)", (message,))
        print("Main message inserted")
        # future input 
        print(entity)
        print(action1)
        print(action2)
        print(action3)
        print(message)
        cur.execute("INSERT INTO pae_data (entity, action1, action2, action3, message) VALUES (%s, %s, %s, %s, %s)", (entity, action1, action2, action3, message,))
        conn.commit()
        cur.close()
        conn.close()
        print(f"Message inserted into DB: {message}")
    except:
        print("Message insert fail 1")

class IRCBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel, nickname, server="10.5.185.72", port=6667):
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
        self.channel = channel

    def on_welcome(self, connection, event):
        print("WELCOME")
        connection.join(self.channel)

    def on_join(self, connection, event):
        print(f"JOIN {self.channel}")

    def on_disconnect(self, connection, event):
        print("DISCONNECT")
        sys.exit(0)

    def on_pubmsg(self, connection, event):
        # Capture the IRC message
        message = event.arguments[0]
        print(f"Received message: {message}")
        try:
            found_entity, action1, action2, action3 = extracted_chat(message)
            if found_entity is not None:
                insert_message(message, found_entity, action1, action2, action3)
        except:
            print("bad input")
        
        # Insert message into PostgreSQL
        

        # Process message from chat
        

def start_irc_bot():
    bot = IRCBot("#app_dev", "Skibby_Mendoza")
    print("IRC listener starting...")
    bot.start()


start_irc_bot()

from chainlit import cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.data.chainlit_data_layer import ChainlitDataLayer




@cl.password_auth_callback
def auth_callback(username: str, password: str):
    # Fetch the user matching username from your database
    # and compare the hashed password with the value stored in the database
    if (username, password) == ("admin", "admin"):
        return cl.User(
            identifier="admin", metadata={"role": "admin", "provider": "credentials"}
        )
    else:
        return None
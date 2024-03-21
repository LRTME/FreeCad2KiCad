*self.socket.send*

- Calculate length of first message  
- First message is type and length of second message  
- Pad first message to reach 8 bytes
- Send length and type (first mesage)
- Send data - encoded json (second message)  

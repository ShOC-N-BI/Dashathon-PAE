* Goals - to recieve data from jchat or dummy data jchat and output it in the correct format for the database to recieve/ingest

- Have functional minimal UI so to include 3 action buttons ie attack, investigate, communicate. Have original message data at the top and have submit button on the bottom. A history section must be included to show what past items have been actioned on. 

- The UI should reflect data from J-chat: the top section will high light the current message that triggered PAE. The three buttons should reflect the battle effect for the triggered message. The UI should be easy to use and simple. 

- Use correct file formatting, define what file format is being used into PAE and what is being used when leaving PAE

- Incoporate AI as needed to help interpret data from the jchat.

- AI should understand the context of the trigger message and highlight the assest/keyworks and then draw a coraltion between possible battle effects and the assest that triggered PAE. 

- AI goals; 
1. break down and noramlize the trigger sentence.
2. align 3 sane, reasonable battle effects to trigger sentence.
3. AI should be prompted as to act on stragetic goals within operating area. I.E; reasonable tasks that align with commanders intent of battle operators.   

- Overview. 
1. create IRC listener that pushes current chat message in our py program.
2. The py program pushes message into AI with prompt and REG citing commanders intent for operating area.
3. AI returns 3 battle effects. 
4. message+ AI response is pushed to UI.
5. user clicks submit/send and pushes that PAE to data base. 

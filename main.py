from fasthtml.common import *
from claudette import *
from monsterui.all import *
from typing import List
from dotenv import load_dotenv
import whisper
import uuid
from pathlib import Path

load_dotenv()

# Style to add blinking to an icon
blink = Style("""
    @keyframes blink {
        0% { opacity: 1; }
        50% { opacity: 0 !important; }
        100% { opacity: 1; }
    }
    .blink {
        animation: blink 1.5s infinite;
    }
""")

hdrs = Theme.blue.headers(), Script(src="/js/record.js"), blink
app, rt = fast_app(hdrs=hdrs, exts='ws', static_path='public')

upload_dir = Path("public")
upload_dir.mkdir(exist_ok=True)

model = whisper.load_model("tiny.en")


# Set up a chat model client and list of messages (https://claudette.answer.ai/)
chat = AsyncClient(models[1])

sp = """You are a helpful assistant."""
messages = [
    # {"role": "assistant", "content": "Hi! How can I help you today? 🚀"},
    # {"role": "user", "content": "Can you help me with MonsterUI?"},
    # {"role": "assistant", "content": "Of course! MonsterUI is a library of components that make it easy to build complex, data-driven web applications. It's built on top of Flask and uses Tailwind CSS for styling."},
]

# Chat components
def UsrMsg(content, content_id):
    if isinstance(content, list):
        content = [x['text'] for x in content if x['type'] == 'text'][0]

    txt_div = Div(content, id=content_id, cls='whitespace-pre-wrap break-words')
    return Div(txt_div,
            cls='max-w-[70%] ml-auto rounded-3xl bg-[#f4f4f4] px-5 py-2.5 rounded-tr-lg')

def AIMsg(txt, content_id):
    avatar = Div(UkIcon('bot', height=24, width=24),
                 cls='h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center')
    txt_div = Div(txt, id=content_id, cls='whitespace-pre-wrap break-words ml-3')
    return Div(
        Div(avatar, txt_div, cls='flex items-start'),
        cls='max-w-[70%] rounded-3xl px-5 py-2.5 rounded-tr-lg'
    )

def ChatMessage(msg_idx):
    msg = messages[msg_idx]
    content_id = f"chat-content-{msg_idx}"
    if msg['role'] == 'user':
        return UsrMsg(msg['content'], content_id)
    else:
        return AIMsg(msg['content'], content_id)

def ChatInput(text=""):
    return (Div(id="image-previews", cls="flex flex-wrap gap-1 mb-2"),  # Container for thumbnails
            Input(placeholder='Message assistant', 
            value=text,
            cls='resize-none border-none outline-none bg-transparent w-full shadow-none ring-0 focus:ring-0 focus:outline-none hover:shadow-none text-lg',
            id='msg-input',
            name='msg',
            hx_swap_oob='true')
    )

def ImageUploadButton():
    return Label(
        Input(type="file", 
              name="file", 
              accept="image/*", 
              id="file-input",
              cls="hidden"),
        UkIcon('paperclip', height=24, width=24, cls='hover:opacity-70 cursor-pointer border-none focus:outline-none'),
        hx_post="/upload", 
        hx_encoding="multipart/form-data",
        hx_trigger="change from:#file-input", 
        hx_swap="beforeend",
        hx_target="#image-previews",

    )


def MultimodalInput():
    return Form(
        Div(
            Div(
                ChatInput(),
                DivFullySpaced(
                    DivHStacked(
                        ImageUploadButton(),
                        Label(
                            UkIconLink('mic', height=24, width=24, 
                                     cls='hover:opacity-70 transition-opacity duration-200',
                                     id='mic-icon'),
                            UkIconLink('circle-stop', height=24, width=24,
                                     cls='hidden hover:opacity-70 transition-opacity duration-200 blink',
                                     id='stop-icon'),
                            id="mic-btn"
                        )
                    ),
                    Button(UkIcon('arrow-right', height=24, width=24), 
                          cls='bg-black text-white rounded-full hover:opacity-70 h-8 w-8 transform -rotate-90'),
                    cls='px-3'
                )
            ), 
            cls='p-2 bg-[#f4f4f4] rounded-3xl'
        ),
        ws_send=True, 
        hx_ext="ws", 
        ws_connect="/wscon"
    )

def chat_layout():
    return Div(
        DivVStacked(
            H1("Chat UI", cls='m-2'),
            Div(
                *[ChatMessage(msg_idx) for msg_idx, msg in enumerate(messages)],
                id="chatlist",
                cls='space-y-6 overflow-y-auto flex-1 w-full' 
            ),
            Footer(
                MultimodalInput(),
                cls='p-4 bg-white border-t w-full'
            ),
            cls='h-screen flex flex-col max-w-3xl mx-auto w-full'
        ),
        cls='container w-full px-4'
    )

# Images 
def Thumbnail(fname):
    return Figure(
        Img(src=f'/{fname}', 
            style="width:48px;height:48px;object-fit:cover;border-radius:4px;"),
        Input(type="hidden", name="images", value=fname),

        cls="inline-flex items-center p-1 m-1 bg-base-200 rounded-lg"
    )

async def save_file(file_obj):
    dest = upload_dir / file_obj.filename
    dest.write_bytes(await file_obj.read())
    return dest

def load_img_bytes(fname: str):
    return (upload_dir / fname).read_bytes()

@rt
async def upload(request):
    form = await request.form()
    file_obj = form['file']
    await save_file(file_obj)
    return Thumbnail(file_obj.filename)

@rt('/transcribe-voice', methods=['POST'])
async def transcribe_voice(request):
    form = await request.form()
    file_obj = form["audio"]
    data = await file_obj.read()
    fname = upload_dir / f"{uuid.uuid4()}.mp3"
    with open(fname, "wb") as f: f.write(data)
    result = model.transcribe(str(fname))
    fname.unlink()
    return result["text"].strip()

@app.route("/")
def get():
    messages = [] # clear session
    return chat_layout()

@app.ws('/wscon')
async def submit(msg: str, images: List[str] = [], send = None):
    # if multiple images, they are returned like [['image1.jpg'], ['image2.jpg']] so we flatten them
    images = L([img for sub in images for img in sub]) if len(images) > 1 else L(images)

    thumbs = images.map(Thumbnail)
    
    # Add user message to conversation history
    imgs = L(images).map(load_img_bytes)
    msg = mk_msg([*imgs, msg])
    messages.append(msg)

    swap = 'beforeend'  # Tell htmx to append new content at end of target element

    # Immediately show user message in chat
    await send(Div((ChatMessage(len(messages)-1), *thumbs), hx_swap_oob=swap, id="chatlist"))
    # await send(Div(ChatMessage(len(messages)-1), hx_swap_oob=swap, id="chatlist"))

    # Clear input field via OOB swap
    await send(ChatInput())

    # Get streaming response from AI
    r = await chat(messages, sp=sp, stream=True)

    # Create empty AI message bubble
    messages.append({"role":"assistant", "content":""})
    # Show empty bubble immediately - creates structure for streaming updates
    await send(Div(ChatMessage(len(messages)-1), hx_swap_oob=swap, id="chatlist"))


    # Stream the response chunks
    async for chunk in r:
        # Update server-side message content
        messages[-1]["content"] += chunk
        # Send chunk to browser - will be inserted into div with matching content_id
        # The ID here matches the inner txt_div in AIMsg function
        await send(Span(chunk, id=f"chat-content-{len(messages)-1}", hx_swap_oob=swap))

# Key points about the streaming mechanism:
# 1. Each message (user/AI) has a unique content_id
# 2. For AI messages, this ID is on the inner text div
# 3. Streamed chunks target this same ID, so they append inside the text div
# 4. This maintains consistent HTML structure during streaming
# 5. The outer bubble structure is created once, then filled gradually with chunks

serve(port=5039)

# QUESTIONS:
# 1. How to do send automatically the <Textarea> form on enter? maybe the button? => For now we'll just use an <Input>
# 2. How to find what is the "most similar" element in monsterUI/franken/tailwind to avoid too many custom classes?

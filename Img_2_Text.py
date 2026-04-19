import importlib.metadata
import pathlib
import re
import sys


def _check_requirements():
    req = pathlib.Path(__file__).parent / "requirements.txt"
    if not req.exists():
        return
    missing = []
    for line in req.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[><=!~\[\s]", line)[0]
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(line)
    if missing:
        print("Missing packages:")
        for p in missing:
            print(f"  {p}")
        print("\nInstall with: pip install -r requirements.txt")
        input("\nPress Enter to exit...")
        sys.exit(1)


_check_requirements()


import os
import requests
import configparser
import easyocr
import multiprocessing
import sys
import textwrap

# Read configuration from the settings file
config = configparser.ConfigParser()
config.read("settings.config")
log_bot_token = config['settings']['log_bot_token']
log_bot_id = config['settings']['log_bot_id']

# # Delete the received image message from the chat if True
delete_img = False

# Function to perform text recognition
def perform_text_recognition(image_path, result_queue, image_count):
    """
    Generate an image from the provided text and save it to the specified file path.

    Args:
        text (str): The text content that you want to convert into an image.
        image_path (str): The file path where the generated image will be saved.

    Returns:
        None

    Raises:
        Exception: If there is an error during image generation or saving.

    Example:
        generate_text_image("Hello, World!", "hello_image.png")
    """

    reader = easyocr.Reader(["en", "nl"], gpu=False, verbose=False)

    with open(os.devnull, 'w') as null_output:
        original_stdout = sys.stdout
        sys.stdout = null_output
        result = reader.readtext(image_path)
        sys.stdout = original_stdout

    result_queue.put(result)

# Function to clear the screen based on the platform
def clear_screen():
    if sys.platform.startswith('win'):
        os.system('cls')
    else:
        os.system('clear')

# Extract text from image data using OCR
def extract_text_from_image(image_data):
    # Create a temporary file to save the image
    with open("temp_image.jpg", "wb") as img_file:
        img_file.write(image_data)

    # Perform text recognition on the saved image
    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=perform_text_recognition, args=("temp_image.jpg", result_queue, 1))
    process.start()
    process.join()
    result = result_queue.get()

    # Extract recognized text and bounding boxes
    recognized_text = [detection[1] for detection in result]
    bounding_boxes = [detection[0] for detection in result]

    # Extracting newlines and paragraphs based on bounding box positions
    lines = []
    current_line = ""

    for box, text in zip(bounding_boxes, recognized_text):
        x, y, w, h = box
        if len(lines) > 0 and len(current_line) > 0 and y > lines[-1][1] + lines[-1][3] * 0.5:
            lines.append((current_line.strip(), x, y, w, h))
            current_line = text
        else:
            current_line += " " + text

    # Adding the last line
    lines.append((current_line.strip(), x, y, w, h))

    # Sorting the lines based on y-coordinate
    lines.sort(key=lambda x: x[2])

    # Reconstructing paragraphs based on vertical position
    paragraphs = []
    current_paragraph = ""

    for line, x, y, w, h in lines:
        if len(paragraphs) > 0 and len(current_paragraph) > 0 and x < paragraphs[-1][3] * 0.5:
            paragraphs.append(current_paragraph.strip())
            current_paragraph = line
        else:
            current_paragraph += " " + line

    # Adding the last paragraph
    paragraphs.append(current_paragraph.strip())

    # Create a formatted text with text wrapping
    formatted_text = ""
    for paragraph in paragraphs:
        wrapped_paragraph = textwrap.fill(paragraph, width=80, break_long_words=False)
        formatted_text += f"Recognized Text:\n{wrapped_paragraph}\n"

    return formatted_text

# Send text message to a chat using the Telegram API
def send_text_to_telegram(chat_id, text):
    send_text = f'https://api.telegram.org/bot{log_bot_token}/sendMessage?chat_id={chat_id}&text={text}'
    requests.get(send_text)

# Process received image and send extracted text back
def process_received_image(image_data, chat_id, message_id):
    extracted_text = extract_text_from_image(image_data)

    send_text_to_telegram(chat_id, extracted_text)

    if delete_img is True:
        # Delete the received image message from the chat
        delete_message_url = f'https://api.telegram.org/bot{log_bot_token}/deleteMessage?chat_id={chat_id}&message_id={message_id}'
        requests.get(delete_message_url)

# Main function to listen for incoming messages and process images
def main():
    print("Listening for incoming messages...")
    send_text_to_telegram(log_bot_id, "I'm ready to convert your photos!")

    # Get the last message ID from the chat
    offset = None

    # Keep listening for incoming messages
    while True:
        response = requests.get(f'https://api.telegram.org/bot{log_bot_token}/getUpdates?offset={offset}').json()
        for update in response['result']:
            if 'message' in update and 'photo' in update['message']:
                chat_id = update['message']['chat']['id']
                message_id = update['message']['message_id']  # Get the message ID
                file_id = update['message']['photo'][-1]['file_id']

                # Fetch the file data directly using getFile and download it
                file_info = requests.get(
                    f'https://api.telegram.org/bot{log_bot_token}/getFile?file_id={file_id}').json()
                file_path = file_info['result']['file_path']
                file_url = f'https://api.telegram.org/file/bot{log_bot_token}/{file_path}'
                image_response = requests.get(file_url).content

                # Process the image and send the extracted text
                # This prevents your bot from repeatedly processing the same updates.
                process_received_image(image_response, chat_id, message_id)  # Pass the message ID

            # Update the offset for the next request.
            offset = update['update_id'] + 1

            # # Exit the lambda function.
            # print("Done!")
            # return

if __name__ == "__main__":
    main()

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import sys
import shutil  # For temporary file cleanup


# Define the Scrapy Item structure.
# This defines the fields that our spider will extract for each real estate listing.
class RealEstateItem(scrapy.Item):
    address = scrapy.Field()  # Address of the property
    sale_price = scrapy.Field()  # Sale price of the property
    home_size_sqft = scrapy.Field()  # Home size in square feet
    lot_size_sqft = scrapy.Field()  # Lot size in square feet


# Define the Scrapy Spider.
# This spider will crawl the specified website, extract the data, and yield RealEstateItem objects.
class RealEstateSpider(scrapy.Spider):
    name = "realestate_scraper"  # Unique name for the spider

    # start_urls will be set dynamically by the main script based on user input.
    # We use __init__ to accept the start_urls argument.
    def __init__(self, start_urls=None, *args, **kwargs):
        super(RealEstateSpider, self).__init__(*args, **kwargs)
        if start_urls:
            # Scrapy expects start_urls as a list, even if it's a single URL.
            self.start_urls = [start_urls]
        else:
            # Raise an error if no starting URL is provided.
            raise ValueError("start_urls must be provided to the spider.")

    # Custom settings for this spider.
    # We configure the output format (CSV) and the fields to be included.
    # We also set a user agent to mimic a real browser request.
    custom_settings = {
        'FEEDS': {
            'output.csv': {
                'format': 'csv',  # Output format is CSV
                'overwrite': True,  # Overwrite the file if it exists
                # Define the order of columns in the CSV.
                'fields': ['address', 'sale_price', 'home_size_sqft', 'lot_size_sqft'],
            },
        },
        # ROBOTSTXT_OBEY should generally be True, but for specific scraping needs,
        # it might be set to False. Be cautious and respectful of website policies.
        'ROBOTSTXT_OBEY': False,
        # A common user agent to avoid being blocked by some websites.
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    # The parse method is called for each downloaded response.
    # It's responsible for parsing the response data and extracting information.
    def parse(self, response):
        # --- IMPORTANT: CUSTOMIZE THESE SELECTORS ---
        # You need to replace these CSS selectors with the actual ones that match the HTML
        # structure of the website you are scraping. Use your browser's developer tools
        # (Inspect Element) to find the correct classes or IDs.

        # Example: Assuming each real estate listing is contained within a <div> with class 'listing'.
        # Adjust 'div.listing' to the correct selector for a single listing container.
        listings = response.css('div.listing')

        # Log a warning if no listings are found, which might indicate incorrect selectors.
        if not listings:
            self.logger.warning(
                "No listings found with the provided selector. Please check the 'div.listing' selector.")
            self.logger.info(f"Response URL: {response.url}")

        # Iterate through each found listing to extract the data.
        for listing in listings:
            item = RealEstateItem()
            # Extract data using specific CSS selectors for each field.
            # .get() is used to retrieve the first matching element's text.
            # If the data is within an attribute, use '::attr(attribute_name)'.
            # For text directly inside a tag, use '::text'.

            # Adjust 'span.address::text' to the correct selector for the property address.
            item['address'] = listing.css('span.address::text').get()
            # Adjust 'span.price::text' for the sale price.
            item['sale_price'] = listing.css('span.price::text').get()
            # Adjust 'span.home-size::text' for the home size.
            item['home_size_sqft'] = listing.css('span.home-size::text').get()
            # Adjust 'span.lot-size::text' for the lot size.
            item['lot_size_sqft'] = listing.css('span.lot-size::text').get()

            # --- Data Cleaning and Normalization ---
            # Remove currency symbols, commas, and 'sqft' text, and strip whitespace.
            if item['sale_price']:
                item['sale_price'] = item['sale_price'].replace('$', '').replace(',', '').strip()
            if item['home_size_sqft']:
                item['home_size_sqft'] = item['home_size_sqft'].replace('sqft', '').replace(',', '').strip()
            if item['lot_size_sqft']:
                item['lot_size_sqft'] = item['lot_size_sqft'].replace('sqft', '').replace(',', '').strip()

            # Yield the item, which will be processed by Scrapy's item pipelines (in this case, the CSV exporter).
            yield item

        # --- Pagination Handling (Optional, but often necessary) ---
        # This part handles navigating to the next page of listings if available.
        # Adjust 'a.next-page::attr(href)' to the selector for the 'Next' page link's href attribute.
        next_page = response.css('a.next-page::attr(href)').get()
        if next_page is not None:
            # Use response.follow to create a new request for the next page and parse it with the same method.
            yield response.follow(next_page, self.parse)


# Function to send the generated CSV file via email.
def send_email(receiver_email, subject, body, attachment_path):
    # Retrieve sender email and password from environment variables for security.
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")

    # Check if environment variables are set.
    if not sender_email or not sender_password:
        print("\nERROR: SENDER_EMAIL and SENDER_PASSWORD environment variables are not set.")
        print("Please set them before running the script. For Gmail, you might need an App Password.")
        print("See: https://support.google.com/accounts/answer/185833?hl=en for Gmail App Passwords.")
        return

    # Create a multipart message and set headers.
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    # Attach the body text to the email.
    msg.attach(MIMEText(body, 'plain'))

    # Attach the CSV file.
    try:
        with open(attachment_path, "rb") as attachment:
            # Create a MIMEBase object for the attachment.
            part = MIMEBase("application", "octet-stream")
            # Set payload to the attachment's raw data.
            part.set_payload(attachment.read())
        # Encode the payload in base64.
        encoders.encode_base64(part)
        # Add header for the attachment, specifying the filename.
        part.add_header(
            "Content-Disposition",
            f"attachment; filename= {os.path.basename(attachment_path)}",
        )
        # Attach the part to the message.
        msg.attach(part)
    except FileNotFoundError:
        print(f"Error: Attachment file not found at {attachment_path}. Skipping email.")
        return

    # Connect to the SMTP server and send the email.
    try:
        # For Gmail, use 'smtp.gmail.com' and port 587 with TLS.
        # Adjust host and port for other email providers (e.g., Outlook, Yahoo).
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Secure the connection with TLS (Transport Layer Security)
        server.login(sender_email, sender_password)  # Login to the email account
        text = msg.as_string()  # Convert the MIMEMultipart object to a string
        server.sendmail(sender_email, receiver_email, text)  # Send the email
        server.quit()  # Disconnect from the server
        print(f"Email sent successfully to {receiver_email}!")
    except Exception as e:
        print(f"Error sending email: {e}")
        print("Please double-check your email credentials, SMTP server settings, and app password.")


# Main script execution block.
# This ensures the code runs only when the script is executed directly.
if __name__ == "__main__":
    print("Welcome to the Website Scraping and Email App!")
    print("---------------------------------------------")

    # Prompt user for the website URL to scrape.
    website_url = input(
        "Please enter the URL of the website you want to scrape (e.g., 'https://example.com/real-estate'): ")
    if not website_url:
        print("Website URL cannot be empty. Exiting.")
        sys.exit(1)  # Exit if no URL is provided

    # Prompt user for the recipient email address.
    receiver_email = input("Please enter the email address where you want to receive the CSV file: ")
    if not receiver_email:
        print("Receiver email cannot be empty. Exiting.")
        sys.exit(1)  # Exit if no email is provided

    output_csv_file = 'output.csv'  # Name of the output CSV file

    print(f"\nStarting the scraping process for {website_url}...")
    print(f"Data will be saved to {output_csv_file}")

    # Scrapy requires a project structure to load settings.
    # We create a temporary, minimal structure for programmatic execution.
    temp_project_dir = 'scrapy_temp_project'
    temp_spiders_dir = os.path.join(temp_project_dir, 'spiders')

    try:
        # Create temporary directories if they don't exist.
        if not os.path.exists(temp_spiders_dir):
            os.makedirs(temp_spiders_dir)

        # Write a dummy settings.py to the temporary project directory.
        # This ensures Scrapy can find necessary configurations like FEEDS.
        with open(os.path.join(temp_project_dir, 'settings.py'), 'w') as f:
            f.write(f"""
BOT_NAME = '{temp_project_dir}'
SPIDER_MODULES = ['{temp_project_dir}.spiders']
NEWSPIDER_MODULE = '{temp_project_dir}.spiders'
ROBOTSTXT_OBEY = False # Set to True for production and respect robots.txt
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
FEEDS = {{
    '{output_csv_file}': {{
        'format': 'csv',
        'overwrite': True,
        'fields': ['address', 'sale_price', 'home_size_sqft', 'lot_size_sqft'],
    }},
}}
# Disable default pipelines if any, or enable custom ones here
ITEM_PIPELINES = {{}}
""")
        # Write the spider code to the temporary spiders directory.
        # This ensures the CrawlerProcess can locate and run our spider.
        with open(os.path.join(temp_spiders_dir, 'realestate_spider.py'), 'w') as f:
            f.write("""
import scrapy

# Item definition copied into the spider file for self-containment in the temporary project
class RealEstateItem(scrapy.Item):
    address = scrapy.Field()
    sale_price = scrapy.Field()
    home_size_sqft = scrapy.Field()
    lot_size_sqft = scrapy.Field()

class RealEstateSpider(scrapy.Spider):
    name = "realestate_scraper"

    def __init__(self, start_urls=None, *args, **kwargs):
        super(RealEstateSpider, self).__init__(*args, **kwargs)
        if start_urls:
            self.start_urls = [start_urls]
        else:
            raise ValueError("start_urls must be provided to the spider.")

    def parse(self, response):
        # IMPORTANT: Replace these CSS selectors with the actual ones for the website you are scraping.
        # Use your browser's developer tools (Inspect Element) to find the correct selectors.
        listings = response.css('div.listing') # Example selector for listing containers

        if not listings:
            self.logger.warning("No listings found with the provided selector. Please check the 'div.listing' selector.")
            self.logger.info(f"Response URL: {response.url}")

        for listing in listings:
            item = RealEstateItem()
            item['address'] = listing.css('span.address::text').get() # Example selector for address
            item['sale_price'] = listing.css('span.price::text').get() # Example selector for sale price
            item['home_size_sqft'] = listing.css('span.home-size::text').get() # Example selector for home size
            item['lot_size_sqft'] = listing.css('span.lot-size::text').get() # Example selector for lot size

            # Clean and normalize data
            if item['sale_price']:
                item['sale_price'] = item['sale_price'].replace('$', '').replace(',', '').strip()
            if item['home_size_sqft']:
                item['home_size_sqft'] = item['home_size_sqft'].replace('sqft', '').replace(',', '').strip()
            if item['lot_size_sqft']:
                item['lot_size_sqft'] = item['lot_size_sqft'].replace('sqft', '').replace(',', '').strip()

            yield item

        # Follow pagination links if available
        next_page = response.css('a.next-page::attr(href)').get() # Example selector for next page link
        if next_page is not None:
            yield response.follow(next_page, self.parse)
""")

        # Set the SCRAPY_SETTINGS_MODULE environment variable to point to our temporary settings file.
        os.environ['SCRAPY_SETTINGS_MODULE'] = f'{temp_project_dir}.settings'
        # Add the current directory (where temp_project_dir is created) to Python's path.
        # This helps Scrapy find the spider module.
        sys.path.append(os.getcwd())

        # Initialize CrawlerProcess with Scrapy project settings.
        process = CrawlerProcess(get_project_settings())
        # Start the crawl process with our spider, passing the user-provided URL.
        process.crawl(RealEstateSpider, start_urls=website_url)
        process.start()  # This blocks until the crawling is finished.

        print("\nScraping complete. Checking for output file...")
        # Check if the CSV file was created and contains data.
        if os.path.exists(output_csv_file) and os.path.getsize(output_csv_file) > 0:
            print(f"CSV file '{output_csv_file}' created successfully.")
            # If the CSV is created, proceed to send the email.
            subject = "Scraped Real Estate Data"
            body = f"Please find the scraped real estate data from {website_url} attached."
            send_email(receiver_email, subject, body, output_csv_file)
        else:
            print(f"Warning: '{output_csv_file}' was not created or is empty. No email sent.")
            print("This could mean no data was scraped. Please verify your spider's CSS selectors.")

    except Exception as e:
        print(f"\nAn error occurred during scraping: {e}")
    finally:
        # Clean up the temporary Scrapy project files after execution.
        if os.path.exists(temp_project_dir):
            print(f"\nCleaning up temporary Scrapy project files in '{temp_project_dir}'...")
            shutil.rmtree(temp_project_dir)
        print("Temporary files cleaned up.")
        # Ensure the output CSV file is also removed for clean runs if desired, or keep it.
        # If you want to automatically remove the output.csv uncomment the next line:
        # if os.path.exists(output_csv_file): os.remove(output_csv_file)
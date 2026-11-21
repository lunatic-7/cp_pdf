
import asyncio
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pypdf import PdfWriter


# ==========================================
# CONFIGURATION
# ==========================================

INPUT_FILE = "problems.txt"
OUTPUT_DIR = Path("output")
OUTPUT_FILE = "codeforces_problems.pdf"

DELAY = 2

ALLOWED_DOMAINS = {
    "codeforces.com",
    "www.codeforces.com",
    "codeforces.me",
    "www.codeforces.me"
}


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def read_links():
    """Read problem URLs from problems.txt."""

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        return [
            line.strip()
            for line in file
            if line.strip() and not line.strip().startswith("#")
        ]


def validate_url(url):
    """Validate Codeforces problem URLs."""

    parsed = urlparse(url)

    if parsed.hostname not in ALLOWED_DOMAINS:
        raise ValueError(f"Invalid Codeforces domain: {url}")

    pattern = r"/(problemset/problem|contest/\d+/problem)/"

    if not re.search(pattern, parsed.path):
        raise ValueError(f"Invalid problem URL: {url}")


def filename_from_url(url):
    """Generate a safe filename."""

    path = urlparse(url).path.strip("/")

    return re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        path
    )


# ==========================================
# WAIT FOR PAGE RENDERING
# ==========================================

async def wait_for_rendering(page):
    """Wait for problem statement, fonts, images and math."""

    await page.locator(
        ".problem-statement"
    ).wait_for(
        state="visible",
        timeout=30000
    )

    # Codeforces first shows $$$...$$$ source, then renders it with MathJax.
    # A processing message can disappear before the formulas are ready.
    await page.wait_for_function("""
        () => {
            const statement = document.querySelector('.problem-statement');
            if (!statement || statement.innerText.includes('$$$')) return false;

            const sources = statement.querySelectorAll('script[type^="math/tex"]');
            const rendered = statement.querySelectorAll('.MathJax, mjx-container');
            return rendered.length >= sources.length &&
                Array.from(rendered).every(element => {
                    const rect = element.getBoundingClientRect();
                    return !element.classList.contains('MathJax_Processing') &&
                        getComputedStyle(element).visibility === 'visible' &&
                        rect.width > 0 && rect.height > 0;
                });
        }
    """, timeout=30000)

    # Wait for fonts and images.
    await page.evaluate("""
        async () => {

            await document.fonts.ready;

            const images = Array.from(
                document.querySelectorAll(
                    '.problem-statement img'
                )
            );

            await Promise.all(
                images.map(img => {

                    if (img.complete) {
                        return Promise.resolve();
                    }

                    return new Promise(resolve => {

                        img.addEventListener(
                            'load', resolve, {once: true}
                        );

                        img.addEventListener(
                            'error', resolve, {once: true}
                        );

                    });
                })
            );

            if (images.some(img => img.naturalWidth === 0)) {
                throw new Error('A problem statement image failed to load');
            }
        }
    """)


# ==========================================
# CLEAN CODEFORCES PAGE
# ==========================================

async def clean_page(page):

    # Hide unwanted elements with CSS.
    await page.add_style_tag(content="""

        /* Website header and navigation */

        #header,
        #footer,
        #sidebar,
        .sidebar,
        .second-level-menu,
        .main-menu,
        .menu-box,
        .top-links,
        .userbox,
        .user-menu,
        .sidebox,
        .roundbox.sidebox,
        .footer,
        .footer-menu,
        .footer-links,
        .lang-chooser {
            display: none !important;
        }

        /* MathJax processing messages */

        #MathJax_Message,
        .MathJax_Message,
        .MathJax_Processing,
        .MathJax_Processing_Message {
            display: none !important;
            visibility: hidden !important;
        }

        /* Remove unnecessary page layout */

        html,
        body {
            background: white !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        #pageContent,
        .content-with-sidebar,
        .content {
            width: 100% !important;
            max-width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Main problem statement */

        .problem-statement {
            display: block !important;
            width: 100% !important;
            max-width: 100% !important;
            margin: 0 auto !important;
            padding: 0 !important;
            font-size: 15px !important;
            font-weight: 500 !important;
            line-height: 1.45 !important;
        }

        .problem-statement .MathJax,
        .problem-statement mjx-container {
            font-size: 108% !important;
        }

        @media print {

            @page {
                size: A4;
                margin: 12mm;
            }

            body {
                background: white !important;
            }

            .problem-statement {
                page-break-inside: auto;
            }

            pre {
                white-space: pre-wrap !important;
                overflow-wrap: anywhere !important;
            }
        }

    """)

    # Remove unwanted HTML elements.
    # IMPORTANT: Do not remove the problem header.

    await page.evaluate("""
        () => {

            const selectors = [

                '#header',
                '#footer',
                '#sidebar',

                '.sidebar',
                '.sidebox',
                '.roundbox.sidebox',

                '.second-level-menu',
                '.main-menu',
                '.menu-box',

                '.top-links',
                '.userbox',
                '.user-menu',

                '.footer',
                '.footer-menu',
                '.footer-links',

                '.lang-chooser',

                '#MathJax_Message',
                '.MathJax_Message',
                '.MathJax_Processing',
                '.MathJax_Processing_Message',

                '.input-output-copier'

            ];

            document.querySelectorAll(
                selectors.join(',')
            ).forEach(element => element.remove());

            // Remove visible math processing text.

            document.querySelectorAll('body *').forEach(
                element => {

                    if (
                        element.children.length === 0 &&
                        /^Processing math:/i.test(
                            element.textContent.trim()
                        )
                    ) {
                        element.remove();
                    }

                }
            );

        }
    """)


# ==========================================
# EXTRACT SINGLE PROBLEM
# ==========================================

async def extract_problem(page, url, index):

    validate_url(url)

    print(f"\n[{index}] Opening: {url}")

    response = await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    if not response or response.status >= 400:
        raise Exception(
            f"Page loading failed: "
            f"{response.status if response else 'Unknown'}"
        )

    await wait_for_rendering(page)

    # Get actual problem title.
    title = await page.locator(
        ".problem-statement > .header > .title"
    ).inner_text()

    print(f"Problem: {title}")

    # Clean webpage.
    await clean_page(page)

    # Generate PDF.
    safe_name = filename_from_url(url)

    pdf_path = OUTPUT_DIR / (
        f"{index:03d}_{safe_name}.pdf"
    )

    await page.pdf(
        path=str(pdf_path),
        format="A4",
        print_background=True,
        prefer_css_page_size=True,
        display_header_footer=False,
        scale=1,
        margin={
            "top": "12mm",
            "bottom": "12mm",
            "left": "12mm",
            "right": "12mm"
        }
    )

    print(f"Saved: {pdf_path}")

    return pdf_path


# ==========================================
# MERGE ALL PDFS
# ==========================================

def merge_pdfs(pdf_files):

    if not pdf_files:
        print("No PDFs available to merge.")
        return

    writer = PdfWriter()

    for pdf_file in pdf_files:
        writer.append(str(pdf_file))

    with open(OUTPUT_FILE, "wb") as output:
        writer.write(output)

    writer.close()

    print("\nPDF merging completed!")


# ==========================================
# MAIN
# ==========================================

async def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    urls = read_links()

    if not urls:
        print("No URLs found in problems.txt")
        return

    pdf_files = []

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000
            },
            device_scale_factor=1
        )

        page = await context.new_page()

        for index, url in enumerate(urls, start=1):

            try:

                pdf_path = await extract_problem(
                    page,
                    url,
                    index
                )

                pdf_files.append(pdf_path)

            except Exception as error:

                print(f"\nFAILED: {url}")
                print(f"Reason: {error}")

            await asyncio.sleep(DELAY)

        await browser.close()

    # Merge successful PDFs.
    merge_pdfs(pdf_files)

    # Final report.
    print("\n" + "=" * 45)
    print("       CODEFORCES PDF GENERATOR")
    print("=" * 45)

    print(f"Total problems : {len(urls)}")
    print(f"Successful     : {len(pdf_files)}")
    print(f"Failed         : {len(urls) - len(pdf_files)}")

    if pdf_files:
        print(f"Combined PDF   : {OUTPUT_FILE}")
        print(f"Individual PDFs: {OUTPUT_DIR}/")

    print("=" * 45)


if __name__ == "__main__":
    asyncio.run(main())

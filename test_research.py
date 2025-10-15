from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.tools.playwright.utils import (
    create_sync_playwright_browser
)
from langchain.agents import initialize_agent, AgentType
from config import small_llm as llm

sync_browser = create_sync_playwright_browser()
toolkit = PlayWrightBrowserToolkit.from_browser(sync_browser=sync_browser)

filtered_tools = []
for t in toolkit.get_tools():
    # For demonstration, skip multi-input tools by name
    if t.name in ("previous_webpage",):  # tools to exclude
        continue
    filtered_tools.append(t)


agent = initialize_agent(filtered_tools, llm, agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True)

query = 'Search Google Scholar for "site:scholar.google.com \\"Verified email at nu.edu.pk\\" Akhtar Jamil"'
agent.run(query)

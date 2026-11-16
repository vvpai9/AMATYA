# World News, Briefings & Global Outage Monitoring

AMATYA keeps you informed of world events and internet infrastructure status through scheduled briefings and real-time outage intelligence (`core/news_service.py`, `actions/news_service.py`).

---

## 1. Automated News Briefings

### Briefing Schedule
- **Startup Debrief:** Automatically presented when AMATYA launches.
- **Thrice-Daily Briefings:**
  - **Morning Briefing:** 08:30
  - **Afternoon Briefing:** 14:00
  - **Evening Briefing:** 20:30

### Selected Categories
News is aggregated, deduplicated, and summarized across 5 core categories:
1. **Geopolitics & World Affairs**
2. **Technology & AI Advances**
3. **Global Conflicts & Security**
4. **Business, Markets & Economy**
5. **Science, Space & Energy**

### Voice Commands:
- *"Brief me on today's news"*
- *"What's happening in tech today?"*
- *"Give me a science and space news update"*
- *"Summarize the morning briefing"*

---

## 2. Real-Time Global Outage Detection (Downdetector & Synthetic Probes)

AMATYA implements dual-layer outage monitoring to alert you before you troubleshoot your local network:

### 1. Downdetector User Disruption Spikes
- Monitors user incident spikes across major service platforms.
- Detects outages where official status pages report "All Systems Operational" but thousands of users cannot log in or authenticate.

### 2. Synthetic HTTP & SSL Latency Probes
- Continuous non-intrusive latency and health checks against critical infrastructure endpoints.

### Monitored Services
- **Cloud & Compute:** Amazon Web Services (AWS), Google Cloud Platform, Microsoft Azure, Cloudflare.
- **Developer Tools:** GitHub, GitLab, Docker Hub, npm.
- **Productivity & Communication:** Microsoft 365, Outlook, Google Workspace, Slack, Zoom.
- **AI Services:** OpenAI, Anthropic Claude, Google Gemini.
- **Social & Media:** Reddit, YouTube, X (Twitter), Discord.

### Clean HUD Card Telemetry
Outages are displayed as clean, structured alert cards in the HUD rather than cluttering paragraphs:
- Service name and affected region.
- Reported symptoms (e.g. "Server Connection", "Login Failure").
- Downdetector user report volume vs. baseline.
- Time of incident onset.

### Voice Commands:
- *"Check for service outages"*
- *"Is GitHub down?"*
- *"Are there any Microsoft 365 or Outlook issues right now?"*
- *"Check if OpenAI or Claude are experiencing problems"*

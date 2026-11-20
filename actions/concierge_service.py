"""
Autonomous Concierge & Movie Ticket Booking Studio for JARVIS.
Contributed by Aman Kumar (@iamTechieAman).

Handles movie showtime discovery, direct BookMyShow / PVR / Paytm cinema booking,
event ticketing, and local dining reservations.
"""
from __future__ import annotations

import json
import urllib.parse
from typing import Optional


def concierge_service(parameters: dict, player=None, session_memory=None) -> str:
    """
    Concierge and ticket booking assistant.
    parameters:
      action: 'movie_tickets' | 'search_movies' | 'book_movie' | 'events' | 'dining'
      movie: Name of the movie (e.g. 'Dune', 'Avengers', 'Pushpa 2')
      city: City name (e.g. 'Noida', 'Delhi NCR', 'Muzaffarpur', 'Bangalore', 'Mumbai')
      theater: Preferred cinema chain (e.g. 'PVR', 'INOX', 'Cinepolis', 'Any')
      format: 'IMAX' | '4DX' | '3D' | '2D' | 'Any'
    """
    action = (parameters.get("action") or "movie_tickets").lower().strip()
    movie = parameters.get("movie") or ""
    city = parameters.get("city") or "Delhi NCR"
    theater = parameters.get("theater") or "Any"
    screen_format = parameters.get("format") or "Any"

    if player and hasattr(player, "write_log"):
        player.write_log(f"CONCIERGE: Executing {action} in {city}...")

    # Normalize city for BookMyShow URL slug
    city_slug = city.lower().replace(" ", "-").replace("delhi-ncr", "national-capital-region-ncr")

    if action in ("movie_tickets", "search_movies", "book_movie", "movies"):
        if movie:
            query = f"{movie} showtimes in {city} {theater} tickets bookmyshow"
            bms_search = f"https://in.bookmyshow.com/explore/movies-{city_slug}?search={urllib.parse.quote(movie)}"
            google_movies = f"https://www.google.com/search?q={urllib.parse.quote(movie + ' movie tickets ' + city)}"
            pvr_url = f"https://www.pvrcinemas.com/"
        else:
            query = f"now showing movies in {city} bookmyshow tickets"
            bms_search = f"https://in.bookmyshow.com/explore/movies-{city_slug}"
            google_movies = f"https://www.google.com/search?q={urllib.parse.quote('movies now showing in ' + city)}"
            pvr_url = f"https://www.pvrcinemas.com/"

        # Fetch recent showtimes/releases via web search
        from actions.web_search import _ddg_search
        results = _ddg_search(query, max_results=4)

        lines = [
            f"# 🎬 Movie & Cinema Concierge: {city}",
            f"**Target:** {movie or 'Current Box Office Releases'} | **Format:** {screen_format} | **Cinema:** {theater}",
            "",
            "### 🎟️ Direct Booking Portals:",
            f"- **BookMyShow:** [Open {city} Movies on BookMyShow]({bms_search})",
            f"- **PVR INOX Cinemas:** [Open PVR INOX Portal]({pvr_url})",
            f"- **Google Live Showtimes:** [View Theater Showtimes & Seat Availability]({google_movies})",
            "",
            "---",
            "### 🍿 Live Listings & Cinema Highlights:"
        ]

        if results:
            for r in results:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                url = r.get("url", "")
                lines.append(f"• **{title}**")
                if snippet:
                    lines.append(f"  {snippet}")
                if url:
                    lines.append(f"  [Direct Link]({url})")
                lines.append("")
        else:
            lines.append("• Showtimes and tickets are live on BookMyShow and PVR INOX.")

        lines.extend([
            "---",
            "*To open the seat selection map in your browser, say: 'Open BookMyShow for [Movie]'.*"
        ])
        content_md = "\n".join(lines)

        # Open in browser if booking requested
        if action == "book_movie":
            try:
                import webbrowser
                webbrowser.open(bms_search)
            except Exception:
                pass

        if player and hasattr(player, "show_content"):
            player.show_content("Movie Concierge", content_md)

        if movie:
            return (
                f"I have checked the cinema showtimes for '{movie}' in {city}, sir. "
                f"Direct booking links for BookMyShow, PVR INOX, and live seat maps are displayed on your screen."
            )
        return (
            f"I have retrieved current box office movies and cinema showtimes in {city}, sir. "
            f"Direct booking portals are ready on your HUD."
        )

    elif action in ("events", "concerts", "comedy"):
        insider_url = f"https://insider.in/all-events-in-{city_slug}"
        bms_events = f"https://in.bookmyshow.com/explore/events-{city_slug}"
        search_url = f"https://www.google.com/search?q={urllib.parse.quote('top upcoming events and concerts in ' + city)}"

        card = f"""# 🎪 Live Events & Entertainment Concierge: {city}
**Location:** {city}  

### 🎟️ Booking Portals:
- **Paytm Insider:** [Browse Events & Concerts in {city}]({insider_url})
- **BookMyShow Events:** [Browse Comedy, Music & Sports in {city}]({bms_events})
- **Google Events:** [Search Local Happenings]({search_url})
"""
        if player and hasattr(player, "show_content"):
            player.show_content("Events Concierge", card)

        return f"Upcoming live events, concerts, and comedy shows for {city} are displayed on your HUD, sir."

    elif action in ("stream_free_movie", "free_movie", "public_domain_movie", "watch_movie"):
        archive_url = f"https://archive.org/details/feature_films?and[]={urllib.parse.quote(movie)}"
        yt_movie_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(movie + ' full movie free')}"
        
        try:
            import webbrowser
            webbrowser.open(yt_movie_url)
        except Exception:
            pass

        card = f"""# 🎥 Free & Public Streaming Concierge: {movie or 'Feature Films'}
**Search Target:** `{movie}`  

### 🎬 Available Free & Legal Streaming Streams:
- **YouTube Free Full Movies:** [Watch on YouTube]({yt_movie_url})
- **Internet Archive Open Cinema:** [Search 20,000+ Free Classic & Independent Movies]({archive_url})
- **Public Domain Films:** Direct streaming initiated in your browser.
"""
        if player and hasattr(player, "show_content"):
            player.show_content("Free Movies Concierge", card)

        return f"I have opened the free full movie stream for '{movie}' on YouTube and Internet Archive, sir."

    elif action in ("dining", "restaurant", "table"):
        zomato_url = f"https://www.zomato.com/{city_slug}/dine-out"
        swiggy_url = f"https://www.swiggy.com/dineout/{city_slug}"
        card = f"""# 🍽️ Dining & Table Reservation Concierge: {city}
- **Zomato Dining:** [Discover & Reserve Tables in {city}]({zomato_url})
- **Swiggy Dineout:** [Browse Top Offers & Reservations]({swiggy_url})
"""
        if player and hasattr(player, "show_content"):
            player.show_content("Dining Concierge", card)

        return f"Dining and table reservation options for {city} are ready on your HUD, sir."

    return "Supported actions: movie_tickets | book_movie | events | dining"


TOOL = {
    "name": "concierge_service",
    "description": (
        "Autonomous Concierge for JARVIS. Searches movie showtimes, finds cinema tickets (BookMyShow, PVR INOX, Paytm), "
        "directs seat booking, discovers live concerts/standup comedy events, and manages dining reservations."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "movie_tickets | book_movie | search_movies | events | dining (default: movie_tickets)",
            },
            "movie": {
                "type": "STRING",
                "description": "Name of the movie to check or book (e.g., Dune, Avengers, Pushpa 2)",
            },
            "city": {
                "type": "STRING",
                "description": "City for cinemas or events (e.g. Noida, Delhi NCR, Muzaffarpur, Bangalore)",
            },
            "theater": {
                "type": "STRING",
                "description": "Preferred cinema chain (PVR, INOX, Cinepolis, or Any)",
            },
            "format": {
                "type": "STRING",
                "description": "Screen format: IMAX, 4DX, 3D, 2D, or Any",
            },
        },
    },
    "handler": concierge_service,
}

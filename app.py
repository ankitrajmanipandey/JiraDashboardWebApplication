import requests
from requests.auth import HTTPBasicAuth
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta, date, timezone
import calendar
import logging
import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import re

logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this in production

# --- Jira Config (for future flexibility, can be loaded from env/config) ---
JIRA_HOST = os.environ.get('JIRA_HOST')
JIRA_USERNAME = os.environ.get('JIRA_USERNAME')
JIRA_API_TOKEN = os.environ.get('JIRA_API_TOKEN')

# Performance configuration
ENABLE_TICKET_ENHANCEMENT = os.environ.get('ENABLE_TICKET_ENHANCEMENT', 'false').lower() == 'true'

# --- Dynamic JQL Queries Configuration from .env ---
def build_jql_queries_from_env():
    queries = {}
    # Find all keys ending with _JQL
    jql_keys = [k for k in os.environ if k.endswith('_JQL')]
    for jql_key in jql_keys:
        prefix = jql_key[:-4]  # Remove _JQL
        jql = os.environ.get(jql_key)
        title = os.environ.get(f'{prefix}_TITLE', prefix)
        desc = os.environ.get(f'{prefix}_DESC', '')
        color = os.environ.get(f'{prefix}_COLOR', '#4CAF50')
        queries[prefix] = {
            'jql': jql,
            'title': title,
            'description': desc,
            'color': color
        }
    return queries

JQL_QUERIES = build_jql_queries_from_env()

# --- Helper Functions ---
def get_customfield_value(field):
    if field is None:
        return ''
    
    # Handle complex JSON objects for Organization and Client Name
    if isinstance(field, list) and len(field) > 0:
        # Handle Organization field which is a list of objects
        if isinstance(field[0], dict) and 'name' in field[0]:
            return field[0]['name']
        return str(field)
    
    if isinstance(field, dict):
        # Handle Client Name field which is a dictionary with 'value' key
        if 'value' in field:
            return field['value']
        # Handle Organization field which might be a single object
        if 'name' in field:
            return field['name']
        if 'displayName' in field:
            return field['displayName']
        return str(field)
    
    if hasattr(field, 'displayName'):
        return field.displayName
    if hasattr(field, 'name'):
        return field.name
    if hasattr(field, 'emailAddress'):
        return field.emailAddress
    if hasattr(field, 'value'):
        return field.value
    
    return str(field)

def format_date(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f%z')
        return dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return date_str

def app_timezone():
    """Timezone used for fortnight boundaries and 'today'."""
    name = os.environ.get('APP_TIMEZONE', '').strip()
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            logger.warning("APP_TIMEZONE %s is unavailable; using the local timezone", name)
    return datetime.now().astimezone().tzinfo or timezone.utc

def fortnight_bounds(year, month, half):
    """Return the inclusive start and end dates of one fortnight.

    30- and 31-day months split on the 15th. February splits on the 14th
    so both halves stay inside the month, including leap years.
    """
    days = calendar.monthrange(year, month)[1]
    if days in (28, 29):
        if half == 1:
            return date(year, month, 1), date(year, month, 14)
        return date(year, month, 15), date(year, month, days)
    if half == 1:
        return date(year, month, 1), date(year, month, 15)
    return date(year, month, 16), date(year, month, days)

def fortnight_half_containing(day):
    first_start, first_end = fortnight_bounds(day.year, day.month, 1)
    if first_start <= day <= first_end:
        return 1
    return 2

def previous_fortnight(year, month, half):
    if half == 2:
        return year, month, 1
    if month == 1:
        return year - 1, 12, 2
    return year, month - 1, 2

def last_six_fortnights(today):
    """Six fortnight periods ending with the one that contains today, oldest first."""
    if isinstance(today, datetime):
        today = today.date()
    year, month = today.year, today.month
    half = fortnight_half_containing(today)
    periods = []
    for _ in range(6):
        periods.append(fortnight_bounds(year, month, half))
        year, month, half = previous_fortnight(year, month, half)
    periods.reverse()
    return periods

def format_fortnight_label(start, end):
    if start.year == end.year:
        return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    return f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"

def parse_jira_created(value):
    """Parse a Jira created timestamp into an aware datetime."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    if len(text) >= 5 and text[-5] in '+-' and text[-3] != ':':
        text = text[:-2] + ':' + text[-2:]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed

def ticket_created_date(created_value, tz):
    parsed = parse_jira_created(created_value)
    if parsed is None:
        return None
    return parsed.astimezone(tz).date()

def count_issues_by_fortnight(issues, periods, today, tz):
    """Count each issue once, using its created date, through today only."""
    counts = [0] * len(periods)
    seen = set()
    for issue in issues or []:
        issue_key = issue.get('key') or issue.get('id')
        if issue_key:
            if issue_key in seen:
                continue
            seen.add(issue_key)
        fields = issue.get('fields') or {}
        created_value = fields.get('created', issue.get('created'))
        created_on = ticket_created_date(created_value, tz)
        if created_on is None or created_on > today:
            continue
        for index, (start, end) in enumerate(periods):
            window_end = end if end < today else today
            if start <= created_on <= window_end:
                counts[index] += 1
                break
    return counts

def project_key_from_jql(jql):
    match = re.search(r'project\s*=\s*"?([A-Za-z][A-Za-z0-9_]*)"?', jql or '', re.IGNORECASE)
    return match.group(1) if match else None

def is_trucap_dashboard(query_key, jql):
    project_key = project_key_from_jql(jql)
    if project_key and project_key.upper() == 'TC':
        return True
    return (query_key or '').lower().startswith('trucap')

def build_fortnight_jql(project_key, start, today):
    """Created-date window from the oldest fortnight through the end of today."""
    end_exclusive = today + timedelta(days=1)
    return (
        f'project = {project_key} AND created >= "{start.isoformat()}" '
        f'AND created < "{end_exclusive.isoformat()}" ORDER BY created ASC'
    )

def generate_summary_by_type(tickets, summary_type):
    """Generate summary based on the specified type (issue_type, client, priority) with status breakdown"""
    summary = {}
    total = 0
    all_statuses = set()  # Collect all unique statuses
    
    for ticket in tickets:
        status = ticket.get('Status', 'Unknown')
        all_statuses.add(status)
        
        if summary_type == 'issue_type':
            # Extract issue type from the ticket
            issue_type = ticket.get('Issue Type', 'Unknown')
            if issue_type not in summary:
                summary[issue_type] = {}
            summary[issue_type][status] = summary[issue_type].get(status, 0) + 1
        elif summary_type == 'client':
            # Extract client from the ticket
            client = ticket.get('Client Name', 'Unknown')
            if client not in summary:
                summary[client] = {}
            summary[client][status] = summary[client].get(status, 0) + 1
        elif summary_type == 'priority':
            # Extract priority from the ticket
            priority = ticket.get('Priority', 'Unknown')
            if priority not in summary:
                summary[priority] = {}
            summary[priority][status] = summary[priority].get(status, 0) + 1
        total += 1
    
    # Calculate totals for each category and status
    category_totals = {}
    status_totals = {}
    grand_total = 0
    
    for category, status_counts in summary.items():
        category_total = sum(status_counts.values())
        category_totals[category] = category_total
        grand_total += category_total
        
        for status, count in status_counts.items():
            status_totals[status] = status_totals.get(status, 0) + count
    
    return summary, total, sorted(list(all_statuses)), category_totals, status_totals, grand_total

def fetch_jira_tickets(jql_query, query_key, max_results=None):
    """Fetch tickets for a JQL query, including status, type, client, and priority."""
    print(f"Fetching tickets for query: {jql_query}")

    search_fields = [
        "summary",
        "status",
        "issuetype",
        "priority",
        "assignee",
        "reporter",
        "created",
        "updated",
        "customfield_11301",
        "customfield_11600",
        "customfield_10002",
        "customfield_10200",
        "timespent",
    ]

    try:
        url = f"{JIRA_HOST}/rest/api/3/search/jql"
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        issues = []
        next_page_token = None
        page_size = max_results if max_results else 100

        while True:
            body = {
                "jql": jql_query,
                "maxResults": page_size,
                "fields": search_fields,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            response = requests.post(
                url,
                json=body,
                headers=headers,
                auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN),
            )
            print(f"Response status: {response.status_code}")

            if response.status_code != 200:
                error_msg = f"Failed to fetch tickets: {response.status_code} {response.text}"
                print(error_msg)
                return [], error_msg

            data = response.json()
            page_issues = data.get("issues", [])
            issues.extend(page_issues)
            print(f"Fetched {len(page_issues)} issues (running total {len(issues)})")

            next_page_token = data.get("nextPageToken")
            if data.get("isLast", True) or not next_page_token:
                break
            if max_results and len(issues) >= max_results:
                issues = issues[:max_results]
                break

        tickets = process_jira_response({"issues": issues}, query_key)
        return tickets, None

    except Exception as e:
        error_msg = f"Error fetching tickets: {e}"
        print(error_msg)
        return [], error_msg

def fetch_issue_created_fields(jql_query):
    """Page through Jira and return issue keys plus created timestamps only."""
    print(f"Fetching created dates for fortnight trend: {jql_query}")
    url = f"{JIRA_HOST}/rest/api/3/search/jql"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    issues = []
    seen = set()
    next_page_token = None

    try:
        while True:
            body = {
                "jql": jql_query,
                "maxResults": 100,
                "fields": ["created"],
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            response = requests.post(
                url,
                json=body,
                headers=headers,
                auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN),
            )
            if response.status_code != 200:
                error_msg = f"Failed to fetch fortnight trend: {response.status_code} {response.text[:500]}"
                logger.error(error_msg)
                print(error_msg)
                return [], error_msg

            data = response.json()
            for issue in data.get("issues", []):
                issue_key = issue.get("key")
                if issue_key:
                    if issue_key in seen:
                        continue
                    seen.add(issue_key)
                issues.append(issue)

            next_page_token = data.get("nextPageToken")
            if data.get("isLast", True) or not next_page_token:
                break

        print(f"Fortnight trend received {len(issues)} unique issues")
        return issues, None
    except Exception as e:
        error_msg = f"Error fetching fortnight trend: {e}"
        logger.exception(error_msg)
        print(error_msg)
        return [], error_msg

def build_fortnight_trend(project_key, today=None, tz=None, issues=None):
    """Build labels and counts for the last six fortnights.

    Pass issues to aggregate local data. Otherwise one paginated Jira search
    loads created dates for the TruCap+ project.
    """
    tz = tz or app_timezone()
    if today is None:
        today = datetime.now(tz).date()
    elif isinstance(today, datetime):
        today = today.astimezone(tz).date() if today.tzinfo else today.date()

    periods = last_six_fortnights(today)
    error = None
    jql = build_fortnight_jql(project_key, periods[0][0], today)
    if issues is None:
        issues, error = fetch_issue_created_fields(jql)

    counts = count_issues_by_fortnight(issues, periods, today, tz)
    return {
        "labels": [format_fortnight_label(start, end) for start, end in periods],
        "counts": counts,
        "error": error,
        "jql": jql,
    }

def process_jira_response(data, query_key):
    """Process the Jira API response and extract ticket data."""
    tickets = []
    
    # Handle different response formats
    issues = []
    if 'issues' in data:
        # Standard search API response
        issues = data.get('issues', [])
    elif 'sections' in data:
        # Issue picker API response
        for section in data.get('sections', []):
            if 'issues' in section:
                issues.extend(section['issues'])
    
    for issue in issues:
        # Handle both full issue objects and summary objects
        if 'fields' in issue:
            # Full issue object from search API
            fields = issue['fields']
            status_field = fields.get('status', {})
            status_category = status_field.get('statusCategory', {}).get('name', '')
            
            # Extract issue type
            issue_type_field = fields.get('issuetype', {})
            issue_type = issue_type_field.get('name', 'Unknown') if issue_type_field else 'Unknown'
            
            # Extract priority
            priority_field = fields.get('priority', {})
            priority = priority_field.get('name', 'None') if priority_field else 'None'
            
            # Extract client name using different custom field IDs based on query
            if 'TRUBOT' in query_key.upper():
                client_name = get_customfield_value(fields.get('customfield_11600'))
            else:
                client_name = get_customfield_value(fields.get('customfield_11301'))
            if not client_name:
                client_name = 'Unknown'
            
            # Extract organization using correct custom field ID
            organization = get_customfield_value(fields.get('customfield_10002'))
            
            # Extract assignee
            assignee_field = fields.get('assignee', {})
            assignee = assignee_field.get('displayName', 'Unassigned') if assignee_field else 'Unassigned'
            
            ticket = {
                'Jira ID': issue['key'],
                'Description': fields.get('summary', ''),
                'Reporter': get_customfield_value(fields.get('reporter')),
                'Assignee': assignee,
                'Created': format_date(fields.get('created', '')),
                'Updated': format_date(fields.get('updated', '')),
                'Status': status_field.get('name', ''),
                'Status Category': status_category,
                'TFS ID': get_customfield_value(fields.get('customfield_10200')),
                'Organization': organization,
                'Issue Type': issue_type,
                'Priority': priority,
                'Client Name': client_name,
                'Time Spent': fields.get('timespent', 0)
            }
        else:
            # Summary object from issue picker API
            ticket = {
                'Jira ID': issue.get('key', ''),
                'Description': issue.get('summaryText', ''),
                'Reporter': issue.get('reporter', 'Unknown'),
                'Assignee': issue.get('assignee', 'Unassigned'),
                'Created': format_date(issue.get('created', '')),
                'Updated': format_date(issue.get('updated', '')),
                'Status': issue.get('status', 'Unknown'),
                'Status Category': issue.get('statusCategory', ''),
                'TFS ID': issue.get('tfsId', ''),
                'Organization': issue.get('organization', ''),
                'Issue Type': issue.get('issueType', 'Unknown'),
                'Priority': issue.get('priority', 'None'),
                'Client Name': issue.get('clientName', 'Unknown'),
                'Time Spent': issue.get('timeSpent', 0)
            }
        
        tickets.append(ticket)
    
    return tickets

def enhance_issue_picker_results(tickets, query_key):
    """Enhance issue picker results by fetching detailed information for each issue."""
    print(f"Enhancing {len(tickets)} tickets with detailed information...")
    
    # For now, let's use the basic information from issue picker to avoid multiple API calls
    # This will make the response much faster while still providing essential data
    enhanced_tickets = []
    
    for ticket in tickets:
        if ticket.get('Jira ID'):
            # Use the basic information from issue picker and enhance only essential fields
            enhanced_ticket = {
                'Jira ID': ticket.get('Jira ID', ''),
                'Description': ticket.get('Description', ''),
                'Reporter': ticket.get('Reporter', 'Unknown'),
                'Assignee': ticket.get('Assignee', 'Unassigned'),
                'Created': ticket.get('Created', ''),
                'Updated': ticket.get('Updated', ''),
                'Status': ticket.get('Status', 'Unknown'),
                'Status Category': ticket.get('Status Category', ''),
                'TFS ID': ticket.get('TFS ID', ''),
                'Organization': ticket.get('Organization', ''),
                'Issue Type': ticket.get('Issue Type', 'Unknown'),
                'Priority': ticket.get('Priority', 'None'),
                'Client Name': ticket.get('Client Name', 'Unknown'),
                'Time Spent': ticket.get('Time Spent', 0)
            }
            enhanced_tickets.append(enhanced_ticket)
        else:
            enhanced_tickets.append(ticket)
    
    print(f"Enhanced {len(enhanced_tickets)} tickets successfully")
    return enhanced_tickets

def test_jira_connection():
    """Test Jira connection and available endpoints."""
    print(f"Testing Jira connection to: {JIRA_HOST}")
    print(f"Username: {JIRA_USERNAME}")
    print(f"API Token: {'*' * len(JIRA_API_TOKEN) if JIRA_API_TOKEN else 'NOT SET'}")
    
    # Test basic connectivity
    try:
        # Test server info endpoint
        server_info_url = f"{JIRA_HOST}/rest/api/2/serverInfo"
        response = requests.get(server_info_url, auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN))
        print(f"Server info endpoint status: {response.status_code}")
        if response.status_code == 200:
            server_info = response.json()
            print(f"Jira version: {server_info.get('versionNumbers', 'Unknown')}")
            print(f"Server title: {server_info.get('serverTitle', 'Unknown')}")
        
        # Test search endpoint availability
        search_endpoints = [
            f"{JIRA_HOST}/rest/api/2/search",
            f"{JIRA_HOST}/rest/api/3/search",
            f"{JIRA_HOST}/rest/api/2/issue/picker"
        ]
        
        for endpoint in search_endpoints:
            try:
                response = requests.get(endpoint, auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN))
                print(f"Endpoint {endpoint}: {response.status_code}")
            except Exception as e:
                print(f"Endpoint {endpoint}: Error - {e}")
        
        # Test a simple search query
        print("\n--- Testing Simple Search Query ---")
        test_jql = "project = TC ORDER BY created DESC"
        print(f"Testing JQL: {test_jql}")
        
        # Try the old API first
        try:
            search_url = f"{JIRA_HOST}/rest/api/2/search"
            params = {"jql": test_jql, "maxResults": 1}
            response = requests.get(search_url, params=params, auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN))
            print(f"Simple search test status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Found {data.get('total', 0)} issues")
                if data.get('issues'):
                    print(f"First issue key: {data['issues'][0]['key']}")
            else:
                print(f"Search failed: {response.text}")
        except Exception as e:
            print(f"Search test error: {e}")
                
    except Exception as e:
        print(f"Connection test failed: {e}")


# Hardcoded admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'pass@123'

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid credentials. Please try again.'
            return render_template('login.html', error=error)
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Only build tile metadata, no ticket fetching
    tile_data = {}
    for query_key, query_config in JQL_QUERIES.items():
        tile_data[query_key] = {
            'title': query_config['title'],
            'description': query_config['description'],
            'color': query_config['color'],
        }

    return render_template('dashboard.html', username=session['username'], tile_data=tile_data)

@app.route('/tile/<query_key>')
def tile_details(query_key):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if query_key not in JQL_QUERIES:
        return redirect(url_for('dashboard'))
    
    query_config = JQL_QUERIES[query_key]
    
    # Add better error handling for API issues
    try:
        tickets, error = fetch_jira_tickets(query_config['jql'], query_key)
        if error:
            print(f"Error fetching tickets for {query_key}: {error}")
            # Continue with empty tickets list to show the UI structure
            tickets = []
    except Exception as e:
        print(f"Exception in fetch_jira_tickets: {e}")
        tickets = []
        error = f"Unexpected error: {str(e)}"
    
    # Get summary type from query parameter (default to 'status')
    summary_type = request.args.get('summary_type', 'status')
    selected_value = request.args.get('value')
    status_filter = request.args.get('status_filter')
    
    # Initialize variables
    summary_data = {}
    total_tickets = 0
    all_statuses = []
    
    # Generate appropriate summary based on type
    if summary_type == 'status':
        # Original status summary
        status_summary = {}
        all_statuses = set()
        for ticket in tickets:
            status = ticket.get('Status', 'Unknown')
            status_summary[status] = status_summary.get(status, 0) + 1
            all_statuses.add(status)
        summary_data = status_summary
        total_tickets = len(tickets)
        all_statuses = sorted(list(all_statuses))
        # For status summary, category_totals and status_totals are the same
        category_totals = status_summary
        status_totals = status_summary
        grand_total = total_tickets
    else:
        # New summary types
        summary_data, total_tickets, all_statuses, category_totals, status_totals, grand_total = generate_summary_by_type(tickets, summary_type)
    
    # Ensure all_statuses is always defined
    if 'all_statuses' not in locals():
        all_statuses = []

    fortnight_trend = None
    if is_trucap_dashboard(query_key, query_config.get('jql', '')):
        project_key = project_key_from_jql(query_config.get('jql', '')) or 'TC'
        try:
            fortnight_trend = build_fortnight_trend(project_key)
        except Exception as e:
            logger.exception("Fortnight trend failed for %s", query_key)
            print(f"Fortnight trend failed for {query_key}: {e}")
            periods = last_six_fortnights(datetime.now(app_timezone()).date())
            fortnight_trend = {
                "labels": [format_fortnight_label(start, end) for start, end in periods],
                "counts": [0] * len(periods),
                "error": f"Unexpected error: {e}",
                "jql": None,
            }
    
    return render_template(
        'tile_details.html',
        username=session['username'],
        title=query_config['title'],
        description=query_config['description'],
        tickets=None,  # Don't show tickets on summary page
        error=error,
        total_tickets=total_tickets,
        summary_data=summary_data,
        summary_type=summary_type,
        selected_value=selected_value,
        status_filter=status_filter,
        all_statuses=all_statuses, # Pass all_statuses to the template
        category_totals=category_totals,
        status_totals=status_totals,
        grand_total=grand_total,
        fortnight_trend=fortnight_trend
    )

@app.route('/tile/<query_key>/tickets')
def tile_tickets(query_key):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if query_key not in JQL_QUERIES:
        return redirect(url_for('dashboard'))
    
    query_config = JQL_QUERIES[query_key]
    
    # Add better error handling for API issues
    try:
        tickets, error = fetch_jira_tickets(query_config['jql'], query_key)
        if error:
            print(f"Error fetching tickets for {query_key}: {error}")
            # Continue with empty tickets list to show the UI structure
            tickets = []
    except Exception as e:
        print(f"Exception in fetch_jira_tickets: {e}")
        tickets = []
        error = f"Unexpected error: {str(e)}"
    
    # Get filter parameters
    summary_type = request.args.get('summary_type', 'status')
    selected_value = request.args.get('value')
    status_filter = request.args.get('status_filter')
    
    # Filter tickets based on parameters
    filtered_tickets = []
    if selected_value:
        if summary_type == 'status':
            filtered_tickets = [t for t in tickets if t.get('Status', 'Unknown') == selected_value]
        elif summary_type == 'issue_type':
            filtered_tickets = [t for t in tickets if t.get('Issue Type', 'Unknown') == selected_value]
        elif summary_type == 'client':
            filtered_tickets = [t for t in tickets if t.get('Client Name', 'Unknown') == selected_value]
        elif summary_type == 'priority':
            filtered_tickets = [t for t in tickets if t.get('Priority', 'Unknown') == selected_value]
        
        # Additional status filter if provided
        if status_filter:
            filtered_tickets = [t for t in filtered_tickets if t.get('Status', 'Unknown') == status_filter]
    
    # Generate page title
    page_title = f"{selected_value}"
    if status_filter:
        page_title += f" - {status_filter}"
    page_title += f" ({summary_type.replace('_', ' ').title()})"
    
    return render_template(
        'tile_tickets.html',
        username=session['username'],
        title=page_title,
        description=query_config['description'],
        tickets=filtered_tickets,
        error=error,
        summary_type=summary_type,
        selected_value=selected_value,
        status_filter=status_filter,
        query_key=query_key,
        JIRA_HOST=JIRA_HOST
    )

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True) 
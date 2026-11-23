# Jira Dashboard Web Application

A modern, tile-based dashboard for viewing Jira tickets with multiple JQL query support.

## Features

- **Tile-based Dashboard**: View multiple JQL queries as interactive tiles
- **Modern UI**: Beautiful, responsive design with glassmorphism effects
- **Detailed Views**: Click on tiles to see detailed ticket information
- **Multiple Queries**: Support for unlimited JQL queries via environment variables
- **Real-time Counts**: Each tile shows the count of tickets matching the query
- **Status Indicators**: Color-coded status badges in detailed views
- **Mobile Responsive**: Works perfectly on all device sizes

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Create Environment File**:
   Create a `.env` file in the root directory with your Jira credentials:
   ```env
   JIRA_HOST=https://your-domain.atlassian.net
   JIRA_USERNAME=your-email@domain.com
   JIRA_API_TOKEN=your-jira-api-token
   ```

3. **Configure JQL Queries**:
   Add your JQL queries to the `.env` file:
   ```env
   # Recent Tickets (default)
   JIRA_JQL=project = "YOUR_PROJECT" AND created >= -15d ORDER BY created DESC
   
   # High Priority Tickets
   JQL_HIGH_PRIORITY=project = "YOUR_PROJECT" AND priority in (Highest, High) ORDER BY priority DESC
   
   # In Progress Tickets
   JQL_IN_PROGRESS=project = "YOUR_PROJECT" AND status in ("In Progress", "Development")
   
   # Blocked Tickets
   JQL_BLOCKED=project = "YOUR_PROJECT" AND status = "Blocked"
   ```

4. **Run the Application**:
   ```bash
   python app.py
   ```

5. **Access the Dashboard**:
   - Open your browser and go to `http://localhost:5000`
   - Login with: `admin` / `admin123`

## Adding New Tiles

To add new tiles to the dashboard, you need to:

1. **Add Environment Variable**: Add your JQL query to the `.env` file:
   ```env
   JQL_YOUR_NEW_QUERY=your custom JQL query here
   ```

2. **Update Configuration**: Add the new query to the `JQL_QUERIES` dictionary in `app.py`:
   ```python
   'your_new_query': {
       'jql': os.environ.get('JQL_YOUR_NEW_QUERY', 'default query here'),
       'title': 'Your Tile Title',
       'description': 'Description of what this tile shows',
       'color': '#your-color-code'
   }
   ```

## Default Tiles

The application comes with 4 default tiles:

1. **Recent Tickets** (Green) - Tickets created in the last 15 days
2. **High Priority** (Red) - High priority tickets
3. **In Progress** (Blue) - Tickets currently in progress
4. **Blocked** (Orange) - Blocked tickets

## Customization

### Colors
Each tile can have a custom color. Use any valid CSS color:
- Hex: `#4CAF50`
- RGB: `rgb(76, 175, 80)`
- Named: `green`

### Tile Information
Each tile displays:
- **Title**: The name of the tile
- **Count**: Number of tickets matching the query
- **Description**: Brief description of what the tile shows
- **Color**: Visual indicator for the tile type

## File Structure

```
JiraDashboardWebApplication/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── templates/
│   ├── login.html        # Login page
│   ├── dashboard.html    # Tile-based dashboard
│   └── tile_details.html # Detailed view for individual tiles
└── README.md            # This file
```

## Security Notes

- Change the default admin credentials in production
- Use environment variables for all sensitive information
- Consider implementing proper authentication for production use

## Troubleshooting

### Common Issues

1. **Connection Errors**: Verify your Jira credentials and host URL
2. **No Tiles Showing**: Check that your JQL queries are valid
3. **Permission Errors**: Ensure your Jira user has access to the projects

### Debug Mode

The application runs in debug mode by default. For production, set:
```python
app.run(debug=False)
```

## Contributing

Feel free to submit issues and enhancement requests! 
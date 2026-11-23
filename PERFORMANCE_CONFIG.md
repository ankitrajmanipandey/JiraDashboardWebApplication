# Performance Configuration Guide

## Fast Response Mode (Recommended)

To get the fastest possible response times, add this to your `.env` file:

```bash
ENABLE_TICKET_ENHANCEMENT=false
```

**Benefits:**
- ⚡ **Lightning fast** response times
- 🚀 Single API call per request
- 💾 Lower memory usage
- 🔄 Better user experience

**What you get:**
- Basic ticket information from issue picker API
- Essential fields: Status, Priority, Issue Type, Client Name
- Sufficient data for dashboard summaries and filtering

## Detailed Response Mode (Optional)

For complete ticket details, enable enhancement:

```bash
ENABLE_TICKET_ENHANCEMENT=true
```

**Benefits:**
- 📊 **Complete ticket information**
- 🔍 All custom fields populated
- 📝 Full descriptions and metadata
- 🎯 Maximum data accuracy

**Trade-offs:**
- ⏱️ Slower response times (2-5x slower)
- 📡 Multiple API calls per request
- 💾 Higher memory usage
- 🔄 May cause timeouts with large datasets

## Dynamic Toggle

You can also toggle enhancement on/off from the dashboard:
- Click the "Enable Enhancement" button to toggle
- Green = Enhancement disabled (fast mode)
- Red = Enhancement enabled (detailed mode)

## Recommended Settings

### For Dashboard Overview
```bash
ENABLE_TICKET_ENHANCEMENT=false
```
- Fast loading of summary tiles
- Quick status and priority breakdowns
- Responsive user interface

### For Detailed Analysis
```bash
ENABLE_TICKET_ENHANCEMENT=true
```
- Complete ticket information
- Full custom field data
- Comprehensive reporting

## Performance Tips

1. **Start with fast mode** - Most users find basic information sufficient
2. **Enable enhancement only when needed** - Use the toggle button for detailed views
3. **Monitor response times** - Check console logs for performance metrics
4. **Consider data caching** - Future versions may include caching for better performance

## Troubleshooting

If you experience slow response times:
1. Check if `ENABLE_TICKET_ENHANCEMENT=true` in your `.env`
2. Verify your Jira API token is valid
3. Check network connectivity to your Jira instance
4. Monitor console logs for API call timing

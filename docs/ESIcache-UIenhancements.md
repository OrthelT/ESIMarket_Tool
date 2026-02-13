# ESI Caching and UI/UX Enhancements

> **STATUS:** Completed

## Project 1: Implement Caching for ESI requests
We pull market history data for our app with a series of API call for each of the nearly 900 items in our watch-list. Often, there is no new data and the call is wasted. The ESI has two methods to signal if data has changed since your last call that can be configured in headers. ESI returns Status Code 304 if data is unchanged. Refactor async history ESI function to utilize these methods. 


### "If-None-Match": "Etag":
- ESI response returns a Etag value in the headers.
- Store this in a .csv file. 
- For each ESI call to the market history endpoint, check if we have stored an Etag for the item. 
- If an etag exists, pass it in the request header as the value of the "If-None-Match" field.

### "If-Modified-Since"": "Last-Modified":
- Store the 'Last-Modified' value returned from the ESI response header. 
- Pass it as the value of "If-Modified-Since" in the request header if it exists for the item. 

### "Data Handeling"
- Check to see if have cached versions of the data corresponding to the 'Etags' and 'Last-Modified'

#### If we have cached versions:
- When the ESI returns a 304 response, if there is a cached version, do not update the row for the item, instead use the last saved version.
- If for some reason we are just missing a cached version of an item that has returned a 304 (which should not be possible unless the user manually deleted it), re-run the request without the cache checks in the header and save the resulting data returned with a 200 status code. 
- Ensure that 304 responses are not treated as errors that trigger any error handling logic 
- Only store new data returned with a 200 status code. 
- Keep a record of requests that resulted in 304 status code (i.e. were unchanged) and include in logs. Display to user after the script has completed.
- Ensure this functionality does not result in incorrect data you should generally either be storing the saved from an earlier run "cache hit" or fresh data if "cached miss"

#### If we do not have a cached version:
- Just run the request normally without the "If-None-Match" or and "If-Modified-Since" in the headers.

### Testing
- Write tests to ensure that this feature works correctly. 

### Configuration
- Make this function enabled by default, but allow it to be disabled in the config file. 

## Project 2: Improve UI/UX
- Progress display feature using rich.Progress works perfectly when running the script with `uv run esi_markets.py`. However when running from setup.py it does not work.
- Displaying progress is an important part of user experience. The progress bars are excellent for this. But, history is still quite slow. It would be nice for the user to see which item is currently being requested. Obtain the type_names for all items in the type_id list. Prior to starting the request. This could be done in the configuration step by populating a type_name column when the type_ids are configured initially. Or added once if they are missing and then reused. These type_names could also be used to label market_stats. 
- Create an entry point for running ESI requests from an interactive interface like we have for run commands from Setup.py. 
- If possible, create a shortcut command for setup and esi that run the setup and interactive market fetch. 



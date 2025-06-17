NASA_SEARCH_URL = "https://images-api.nasa.gov/search"


async def search_images(query: str):
    # TODO: Make async HTTP request to NASA API with query
    # TODO: Parse and return relevant image data
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(NASA_SEARCH_URL, params={"q": query})
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()

        # Extract relevant image information
        images = []
        for item in data.get("collection", {}).get("items", []):
            if "links" in item:
                for link in item["links"]:
                    if link.get("rel") == "preview":
                        images.append(
                            {
                                "title": item.get("data", [{}])[0].get(
                                    "title", "No title"
                                ),
                                "url": link.get("href"),
                            }
                        )
        return images

    # Example usage:
    # images = await search_images("Mars")
    #     # print(images)  # Should print a list of image dictionaries with title and URL
    # Note: This function is asynchronous and should be called within an async context.

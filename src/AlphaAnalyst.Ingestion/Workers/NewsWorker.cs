using AlphaAnalyst.Ingestion.Models;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AlphaAnalyst.Ingestion.Workers;

/// <summary>
/// Background worker that periodically polls a news API (e.g., NewsAPI.org or
/// Marketaux) for financial news and forwards articles to the downstream RAG hub.
/// </summary>
public class NewsWorker : BackgroundService
{
    private readonly ILogger<NewsWorker> _logger;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IConfiguration _configuration;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public NewsWorker(
        ILogger<NewsWorker> logger,
        IHttpClientFactory httpClientFactory,
        IConfiguration configuration)
    {
        _logger = logger;
        _httpClientFactory = httpClientFactory;
        _configuration = configuration;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("News Worker started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await FetchAndPublishArticlesAsync(stoppingToken);
            }
            catch (OperationCanceledException)
            {
                // Expected on shutdown.
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Unhandled error in NewsWorker.");
            }

            var intervalSeconds = _configuration.GetValue<int>("News:PollingIntervalSeconds", 600);
            await Task.Delay(TimeSpan.FromSeconds(intervalSeconds), stoppingToken);
        }

        _logger.LogInformation("News Worker stopped.");
    }

    private async Task FetchAndPublishArticlesAsync(CancellationToken cancellationToken)
    {
        var apiKey = _configuration["News:ApiKey"];
        if (string.IsNullOrWhiteSpace(apiKey))
        {
            _logger.LogWarning("News:ApiKey is not configured. Skipping news fetch.");
            return;
        }

        var tickers = _configuration.GetSection("News:Tickers").Get<string[]>()
                      ?? ["AAPL", "MSFT", "GOOGL"];

        var client = _httpClientFactory.CreateClient("NewsApi");

        foreach (var ticker in tickers)
        {
            _logger.LogInformation("Fetching news for ticker {Ticker}…", ticker);

            var url = $"https://newsapi.org/v2/everything" +
                      $"?q={Uri.EscapeDataString(ticker)}" +
                      $"&from={DateTime.UtcNow.AddHours(-24):yyyy-MM-ddTHH:mm:ssZ}" +
                      $"&sortBy=publishedAt&language=en&pageSize=20" +
                      $"&apiKey={apiKey}";

            var response = await client.GetAsync(url, cancellationToken);
            response.EnsureSuccessStatusCode();

            var result = await response.Content.ReadFromJsonAsync<NewsApiResponse>(
                JsonOptions, cancellationToken);

            if (result?.Articles is null || result.Articles.Count == 0)
            {
                _logger.LogInformation("No news articles returned for ticker {Ticker}.", ticker);
                continue;
            }

            foreach (var apiArticle in result.Articles)
            {
                var article = MapToArticle(apiArticle, ticker);
                _logger.LogInformation(
                    "Fetched news article: \"{Title}\" from {Source}",
                    article.Title, article.Source);

                // TODO: publish article to message bus / persistence layer.
                await PublishArticleAsync(article, cancellationToken);
            }
        }
    }

    private static NewsArticle MapToArticle(ApiArticle src, string ticker) => new()
    {
        Title = src.Title ?? string.Empty,
        Source = src.Source?.Name ?? string.Empty,
        Author = src.Author ?? string.Empty,
        Url = src.Url ?? string.Empty,
        Summary = src.Description,
        Content = src.Content,
        PublishedAt = src.PublishedAt ?? DateTime.UtcNow,
        FetchedAt = DateTime.UtcNow,
        Tickers = [ticker],
    };

    private Task PublishArticleAsync(NewsArticle article, CancellationToken cancellationToken)
    {
        // Placeholder: emit to Azure Service Bus, Kafka, or write to a store.
        // Replace with actual publishing logic (e.g., IMessagePublisher).
        _logger.LogDebug("Publishing article \"{Title}\" to downstream.", article.Title);
        return Task.CompletedTask;
    }

    // ── NewsAPI response shape ───────────────────────────────────────────────

    private sealed class NewsApiResponse
    {
        [JsonPropertyName("status")]
        public string? Status { get; set; }

        [JsonPropertyName("totalResults")]
        public int TotalResults { get; set; }

        [JsonPropertyName("articles")]
        public List<ApiArticle>? Articles { get; set; }
    }

    private sealed class ApiArticle
    {
        [JsonPropertyName("source")]
        public ApiSource? Source { get; set; }

        [JsonPropertyName("author")]
        public string? Author { get; set; }

        [JsonPropertyName("title")]
        public string? Title { get; set; }

        [JsonPropertyName("description")]
        public string? Description { get; set; }

        [JsonPropertyName("url")]
        public string? Url { get; set; }

        [JsonPropertyName("content")]
        public string? Content { get; set; }

        [JsonPropertyName("publishedAt")]
        public DateTime? PublishedAt { get; set; }
    }

    private sealed class ApiSource
    {
        [JsonPropertyName("id")]
        public string? Id { get; set; }

        [JsonPropertyName("name")]
        public string? Name { get; set; }
    }
}

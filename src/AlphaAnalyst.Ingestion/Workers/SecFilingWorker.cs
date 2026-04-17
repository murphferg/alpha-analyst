using AlphaAnalyst.Ingestion.Models;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AlphaAnalyst.Ingestion.Workers;

/// <summary>
/// Background worker that periodically fetches recent SEC filings from the EDGAR Full-Text
/// Search API and forwards them to the downstream RAG hub for processing.
/// </summary>
public class SecFilingWorker : BackgroundService
{
    private readonly ILogger<SecFilingWorker> _logger;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IConfiguration _configuration;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public SecFilingWorker(
        ILogger<SecFilingWorker> logger,
        IHttpClientFactory httpClientFactory,
        IConfiguration configuration)
    {
        _logger = logger;
        _httpClientFactory = httpClientFactory;
        _configuration = configuration;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("SEC Filing Worker started.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await FetchAndPublishFilingsAsync(stoppingToken);
            }
            catch (OperationCanceledException)
            {
                // Expected on shutdown; do not log as error.
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Unhandled error in SecFilingWorker.");
            }

            var intervalSeconds = _configuration.GetValue<int>("SecFiling:PollingIntervalSeconds", 300);
            await Task.Delay(TimeSpan.FromSeconds(intervalSeconds), stoppingToken);
        }

        _logger.LogInformation("SEC Filing Worker stopped.");
    }

    private async Task FetchAndPublishFilingsAsync(CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient("Edgar");

        // EDGAR full-text search — retrieve most-recent 10-K and 10-Q filings.
        var formTypes = _configuration.GetSection("SecFiling:FormTypes").Get<string[]>()
                        ?? ["10-K", "10-Q", "8-K"];

        foreach (var formType in formTypes)
        {
            _logger.LogInformation("Fetching SEC {FormType} filings…", formType);

            var url = $"https://efts.sec.gov/LATEST/search-index?q=%22{Uri.EscapeDataString(formType)}%22" +
                      $"&dateRange=custom&startdt={DateTime.UtcNow.AddDays(-1):yyyy-MM-dd}" +
                      $"&enddt={DateTime.UtcNow:yyyy-MM-dd}&forms={Uri.EscapeDataString(formType)}";

            var response = await client.GetAsync(url, cancellationToken);
            response.EnsureSuccessStatusCode();

            var result = await response.Content.ReadFromJsonAsync<EdgarSearchResult>(
                JsonOptions, cancellationToken);

            if (result?.Hits?.Hits is null)
            {
                _logger.LogWarning("No SEC filings returned for form type {FormType}.", formType);
                continue;
            }

            foreach (var hit in result.Hits.Hits)
            {
                var filing = MapToFiling(hit);
                _logger.LogInformation(
                    "Fetched SEC filing: {AccessionNumber} ({FormType}) for {Company}",
                    filing.AccessionNumber, filing.FormType, filing.CompanyName);

                // TODO: publish filing to message bus / persistence layer.
                await PublishFilingAsync(filing, cancellationToken);
            }
        }
    }

    private static SecFiling MapToFiling(EdgarHit hit) => new()
    {
        AccessionNumber = hit.Id ?? string.Empty,
        Cik = hit.Source?.EntityId ?? string.Empty,
        CompanyName = hit.Source?.DisplayNames?.FirstOrDefault() ?? string.Empty,
        FormType = hit.Source?.FormType ?? string.Empty,
        FilingDate = hit.Source?.FilingDate is string d && DateOnly.TryParse(d, out var date)
            ? date
            : DateOnly.FromDateTime(DateTime.UtcNow),
        DocumentUrl = hit.Source?.FileDate is not null
            ? $"https://www.sec.gov/Archives/edgar/data/{hit.Source.EntityId}/{hit.Id?.Replace("-", "")}/{hit.Id}-index.htm"
            : string.Empty,
        Description = hit.Source?.HighlightedText,
        FetchedAt = DateTime.UtcNow,
    };

    private Task PublishFilingAsync(SecFiling filing, CancellationToken cancellationToken)
    {
        // Placeholder: emit to Azure Service Bus, Kafka, or write to a store.
        // Replace with actual publishing logic (e.g., IMessagePublisher).
        _logger.LogDebug("Publishing filing {AccessionNumber} to downstream.", filing.AccessionNumber);
        return Task.CompletedTask;
    }

    // ── EDGAR API response shape ─────────────────────────────────────────────

    private sealed class EdgarSearchResult
    {
        [JsonPropertyName("hits")]
        public EdgarHits? Hits { get; set; }
    }

    private sealed class EdgarHits
    {
        [JsonPropertyName("hits")]
        public List<EdgarHit>? Hits { get; set; }
    }

    private sealed class EdgarHit
    {
        [JsonPropertyName("_id")]
        public string? Id { get; set; }

        [JsonPropertyName("_source")]
        public EdgarSource? Source { get; set; }
    }

    private sealed class EdgarSource
    {
        [JsonPropertyName("entity_id")]
        public string? EntityId { get; set; }

        [JsonPropertyName("display_names")]
        public List<string>? DisplayNames { get; set; }

        [JsonPropertyName("form_type")]
        public string? FormType { get; set; }

        [JsonPropertyName("file_date")]
        public string? FileDate { get; set; }

        [JsonPropertyName("filing_date")]
        public string? FilingDate { get; set; }

        [JsonPropertyName("period_of_report")]
        public string? PeriodOfReport { get; set; }

        [JsonPropertyName("highlighted_text")]
        public string? HighlightedText { get; set; }
    }
}

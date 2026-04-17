using AlphaAnalyst.Gateway.Models;
using Microsoft.AspNetCore.Mvc;

namespace AlphaAnalyst.Gateway.Controllers;

/// <summary>
/// Provides AI-generated investment insights for a given equity ticker.
/// </summary>
[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class InsightsController : ControllerBase
{
    private readonly ILogger<InsightsController> _logger;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IConfiguration _configuration;

    public InsightsController(
        ILogger<InsightsController> logger,
        IHttpClientFactory httpClientFactory,
        IConfiguration configuration)
    {
        _logger = logger;
        _httpClientFactory = httpClientFactory;
        _configuration = configuration;
    }

    /// <summary>
    /// Returns the latest insights for the specified ticker symbol.
    /// </summary>
    /// <param name="ticker">Equity ticker symbol (e.g. AAPL).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A list of <see cref="Insight"/> objects.</returns>
    [HttpGet("{ticker}")]
    [ProducesResponseType(typeof(IEnumerable<Insight>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status502BadGateway)]
    public async Task<ActionResult<IEnumerable<Insight>>> GetInsightsAsync(
        string ticker,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(ticker))
            return BadRequest("Ticker symbol is required.");

        ticker = ticker.ToUpperInvariant();
        _logger.LogInformation("Fetching insights for {Ticker}", ticker);

        try
        {
            var ragHubBaseUrl = _configuration["RagHub:BaseUrl"]
                                ?? "http://localhost:8000";

            var client = _httpClientFactory.CreateClient("RagHub");
            var response = await client.GetAsync(
                $"{ragHubBaseUrl}/insights/{ticker}", cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning(
                    "RAG Hub returned {StatusCode} for ticker {Ticker}",
                    response.StatusCode, ticker);

                return StatusCode(
                    StatusCodes.Status502BadGateway,
                    $"Upstream error: {response.StatusCode}");
            }

            var insights = await response.Content
                .ReadFromJsonAsync<IEnumerable<Insight>>(cancellationToken: cancellationToken)
                ?? Enumerable.Empty<Insight>();

            return Ok(insights);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Failed to reach RAG Hub for ticker {Ticker}", ticker);
            return StatusCode(StatusCodes.Status502BadGateway, "RAG Hub is unavailable.");
        }
    }

    /// <summary>
    /// Triggers a fresh synthesis for the given ticker and returns the new insights.
    /// </summary>
    /// <param name="ticker">Equity ticker symbol.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    [HttpPost("{ticker}/synthesize")]
    [ProducesResponseType(typeof(IEnumerable<Insight>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status502BadGateway)]
    public async Task<ActionResult<IEnumerable<Insight>>> SynthesizeAsync(
        string ticker,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(ticker))
            return BadRequest("Ticker symbol is required.");

        ticker = ticker.ToUpperInvariant();
        _logger.LogInformation("Triggering synthesis for {Ticker}", ticker);

        try
        {
            var ragHubBaseUrl = _configuration["RagHub:BaseUrl"]
                                ?? "http://localhost:8000";

            var client = _httpClientFactory.CreateClient("RagHub");
            var response = await client.PostAsync(
                $"{ragHubBaseUrl}/synthesize/{ticker}", null, cancellationToken);

            response.EnsureSuccessStatusCode();

            var insights = await response.Content
                .ReadFromJsonAsync<IEnumerable<Insight>>(cancellationToken: cancellationToken)
                ?? Enumerable.Empty<Insight>();

            return Ok(insights);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Failed to synthesize insights for ticker {Ticker}", ticker);
            return StatusCode(StatusCodes.Status502BadGateway, "RAG Hub is unavailable.");
        }
    }
}

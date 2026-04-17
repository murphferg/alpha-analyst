using AlphaAnalyst.Gateway.Models;
using Microsoft.AspNetCore.Mvc;

namespace AlphaAnalyst.Gateway.Controllers;

/// <summary>
/// Provides a read-only audit trail of API activity.
/// </summary>
[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class AuditController : ControllerBase
{
    private readonly ILogger<AuditController> _logger;
    private readonly IConfiguration _configuration;

    public AuditController(
        ILogger<AuditController> logger,
        IConfiguration configuration)
    {
        _logger = logger;
        _configuration = configuration;
    }

    /// <summary>
    /// Returns recent audit entries, optionally filtered by user or resource.
    /// </summary>
    /// <param name="userId">Optional user ID filter.</param>
    /// <param name="resource">Optional resource name filter (e.g. "Insights").</param>
    /// <param name="limit">Maximum number of entries to return (default 50, max 200).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    [HttpGet]
    [ProducesResponseType(typeof(IEnumerable<AuditEntry>), StatusCodes.Status200OK)]
    public Task<ActionResult<IEnumerable<AuditEntry>>> GetAuditEntriesAsync(
        [FromQuery] string? userId,
        [FromQuery] string? resource,
        [FromQuery] int limit,
        CancellationToken cancellationToken)
    {
        limit = Math.Clamp(limit == 0 ? 50 : limit, 1, 200);

        _logger.LogInformation(
            "Audit query: userId={UserId} resource={Resource} limit={Limit}",
            userId, resource, limit);

        // TODO: replace stub with actual persistence query (e.g. CosmosDB / SQL).
        var stub = Enumerable.Range(1, Math.Min(limit, 5)).Select(i => new AuditEntry
        {
            Id = Guid.NewGuid().ToString(),
            RequestId = Guid.NewGuid().ToString(),
            UserId = userId ?? "system",
            Action = "GET",
            Resource = resource ?? "Insights",
            StatusCode = 200,
            DurationMs = Random.Shared.Next(10, 350),
            Timestamp = DateTime.UtcNow.AddMinutes(-i),
        });

        return Task.FromResult<ActionResult<IEnumerable<AuditEntry>>>(Ok(stub));
    }

    /// <summary>
    /// Returns the audit entry with the given <paramref name="id"/>.
    /// </summary>
    [HttpGet("{id}")]
    [ProducesResponseType(typeof(AuditEntry), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<AuditEntry> GetById(string id)
    {
        _logger.LogInformation("Fetching audit entry {Id}", id);

        // TODO: replace with actual lookup.
        return NotFound($"Audit entry '{id}' not found.");
    }
}

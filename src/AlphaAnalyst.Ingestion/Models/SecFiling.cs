namespace AlphaAnalyst.Ingestion.Models;

public class SecFiling
{
    public string AccessionNumber { get; set; } = string.Empty;
    public string Cik { get; set; } = string.Empty;
    public string CompanyName { get; set; } = string.Empty;
    public string FormType { get; set; } = string.Empty;
    public DateOnly FilingDate { get; set; }
    public string DocumentUrl { get; set; } = string.Empty;
    public string? Description { get; set; }
    public DateTime FetchedAt { get; set; } = DateTime.UtcNow;
}

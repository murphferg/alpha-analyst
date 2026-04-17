namespace AlphaAnalyst.Gateway.Models;

public class Insight
{
    public string Id { get; set; } = Guid.NewGuid().ToString();
    public string Ticker { get; set; } = string.Empty;
    public string Type { get; set; } = string.Empty; // e.g. "Fundamental", "Sentiment", "TechnicalRisk"
    public string Summary { get; set; } = string.Empty;
    public string? DetailedAnalysis { get; set; }
    public double ConfidenceScore { get; set; }
    public string[] Sources { get; set; } = [];
    public DateTime GeneratedAt { get; set; } = DateTime.UtcNow;
}

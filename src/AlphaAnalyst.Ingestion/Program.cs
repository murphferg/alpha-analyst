using AlphaAnalyst.Ingestion.Workers;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddHttpClient("Edgar", client =>
{
    client.BaseAddress = new Uri("https://efts.sec.gov/");
    client.DefaultRequestHeaders.Add(
        "User-Agent",
        builder.Configuration["SecFiling:UserAgent"] ?? "AlphaAnalyst/1.0 contact@example.com");
});

builder.Services.AddHttpClient("NewsApi", client =>
{
    client.BaseAddress = new Uri("https://newsapi.org/");
});

builder.Services.AddHostedService<SecFilingWorker>();
builder.Services.AddHostedService<NewsWorker>();

var host = builder.Build();
host.Run();

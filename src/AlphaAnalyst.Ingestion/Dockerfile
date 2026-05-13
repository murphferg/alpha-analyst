FROM mcr.microsoft.com/dotnet/aspnet:10.0-preview AS base
WORKDIR /app

FROM mcr.microsoft.com/dotnet/sdk:10.0-preview AS build
WORKDIR /src
COPY AlphaAnalyst.Ingestion/AlphaAnalyst.Ingestion.csproj AlphaAnalyst.Ingestion/
RUN dotnet restore AlphaAnalyst.Ingestion/AlphaAnalyst.Ingestion.csproj
COPY AlphaAnalyst.Ingestion/ AlphaAnalyst.Ingestion/
WORKDIR /src/AlphaAnalyst.Ingestion
RUN dotnet publish -c Release -o /app/publish /p:UseAppHost=false

FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENV DOTNET_ENVIRONMENT=Production
ENTRYPOINT ["dotnet", "AlphaAnalyst.Ingestion.dll"]

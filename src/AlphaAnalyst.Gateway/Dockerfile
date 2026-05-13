FROM mcr.microsoft.com/dotnet/aspnet:10.0-preview AS base
WORKDIR /app
EXPOSE 8080

FROM mcr.microsoft.com/dotnet/sdk:10.0-preview AS build
WORKDIR /src
COPY AlphaAnalyst.Gateway/AlphaAnalyst.Gateway.csproj AlphaAnalyst.Gateway/
RUN dotnet restore AlphaAnalyst.Gateway/AlphaAnalyst.Gateway.csproj
COPY AlphaAnalyst.Gateway/ AlphaAnalyst.Gateway/
WORKDIR /src/AlphaAnalyst.Gateway
RUN dotnet publish -c Release -o /app/publish /p:UseAppHost=false

FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:8080
ENV ASPNETCORE_ENVIRONMENT=Production
ENTRYPOINT ["dotnet", "AlphaAnalyst.Gateway.dll"]

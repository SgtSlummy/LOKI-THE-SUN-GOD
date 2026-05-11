using System;
using Microsoft.UI.Xaml.Controls;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace LokiOperator;

/// <summary>
/// The main content page displayed inside the application window.
/// Add your UI logic, event handlers, and data binding here.
/// </summary>
public sealed partial class MainPage : Page
{
    public MainPage()
    {
        InitializeComponent();

        var dashboardUrl =
            Environment.GetEnvironmentVariable("LOKI_DASHBOARD_URL")
            ?? Environment.GetEnvironmentVariable("DASHBOARD_PUBLIC_URL")
            ?? "http://127.0.0.1:7331";
        DashboardWebView.Source = new Uri(dashboardUrl);
    }
}

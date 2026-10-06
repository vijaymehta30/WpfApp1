using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Navigation;
using System.Windows.Shapes;

namespace WpfApp1
{
    /// <summary>
    /// Interaction logic for MainWindow.xaml
    /// </summary>
    public partial class MainWindow : Window
    {
        public MainWindow()
        {
            InitializeComponent();
            tbHello.Text = "Hello, World! 2";
            btnClick.Content = "Click Me 2";
        }

        private void CheckBox_Checked(object sender, RoutedEventArgs e)
        {

        }

        private void btnClick_Click(object sender, RoutedEventArgs e)
        {

        }
    }
}
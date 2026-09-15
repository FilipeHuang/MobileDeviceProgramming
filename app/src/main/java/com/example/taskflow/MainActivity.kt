package com.example.taskflow

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import com.example.taskflow.ui.theme.TaskFlowTheme
//new imports
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.remember
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TaskFlowTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    Greeting(
                        name = "All",
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }
}

@Composable
fun Greeting(name: String, modifier: Modifier = Modifier) {
    var count by remember {mutableStateOf(0)}
    Column(modifier = modifier.padding(16.dp)) {
        Text(text = "Hello $name!")
        Text(
            text = "Mobile Device Programming week 0",
            modifier = Modifier.padding(top = 8.dp)
        )
        Text(
            text = "Clicked ${count} ${if(count==1 || count==0) "time" else "times"}"
        )
        Button(
            onClick = {count++},
            modifier = Modifier.padding(top = 16.dp)
        ) { Text("Click")}}

}

@Preview(showBackground = true)
@Composable
fun GreetingPreview() {
    TaskFlowTheme {
        Greeting("Android")
    }
}
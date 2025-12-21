use letta::ClientBuilder;
use letta::types::{CreateMessagesRequest, MessageCreate, LettaMessageUnion, LettaId};
use std::time::Duration;
use std::str::FromStr;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Create client with 600 second timeout for slow local LLMs
    let client = ClientBuilder::new()
        .base_url("http://localhost:8283")
        .timeout(Duration::from_secs(600))
        .build()?;

    // Your agent ID
    let agent_id = LettaId::from_str("agent-d93e0978-c442-4425-ba5d-a4bf3c4096e5")?;

    println!("Sending message to agent {}...", agent_id);

    // Send a message
    let request = CreateMessagesRequest {
        messages: vec![MessageCreate::user("How many turns in this conversation?")],
        ..Default::default()
    };

    let response = client
        .messages()
        .create(&agent_id, request)
        .await?;

    // Print the response
    for msg in response.messages {
        match &msg {
            LettaMessageUnion::ReasoningMessage(m) => {
                println!("Reasoning: {}", m.reasoning);
            }
            LettaMessageUnion::ToolReturnMessage(t) => {
                println!("Tool Return: {:?}", t.tool_return);
            }
            LettaMessageUnion::AssistantMessage(m) => {
                println!("Assistant: {}", m.content);
            }
            LettaMessageUnion::ToolCallMessage(t) => {
                println!("Tool Call: {} - {:?}", t.tool_call.name, t.tool_call.arguments);
            }
            _ => {
                println!("Other message: {:?}", msg);
            }
        }
        println!();
    }

    Ok(())
}

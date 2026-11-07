/* Keep the current question and the beginning of its answer together in view. */
let followNewReply=false,chatResizeObserver=null,observedTurn=null;
function latestChatTurn(){return document.querySelector("#conversation .chat-turn:last-of-type");}
function questionFocusTop(question,pane){
  const box=question.getBoundingClientRect();
  return Math.max(box.top,box.bottom-Math.min(140,pane.clientHeight*.3));
}
function measureChatSpace(){
  const pane=document.getElementById("chat-scroll"),turn=latestChatTurn(),space=document.getElementById("conversation-space");
  if(!turn||!space)return;
  const question=turn.querySelector(".question-bubble");
  const height=Math.max(0,pane.clientHeight-(turn.getBoundingClientRect().bottom-questionFocusTop(question,pane))-12);
  const value=Math.ceil(height)+"px";
  if(space.style.height!==value)space.style.height=value;
}
function showLatestReplyButton(){
  const pane=document.getElementById("chat-scroll"),turn=latestChatTurn(),button=document.getElementById("latest-reply");
  if(!turn){button.hidden=true;return;}
  const view=pane.getBoundingClientRect(),box=turn.getBoundingClientRect();
  button.hidden=box.top<view.bottom-40&&box.bottom>view.top+30;
}
function focusLatestQuestion(){
  const pane=document.getElementById("chat-scroll"),question=latestChatTurn()?.querySelector(".question-bubble");
  if(!question)return;
  measureChatSpace();
  pane.scrollTop+=questionFocusTop(question,pane)-pane.getBoundingClientRect().top-12;
  showLatestReplyButton();
}
function updateChatScroll(force,changed){
  const turn=latestChatTurn();
  if(turn!==observedTurn){
    if(observedTurn)chatResizeObserver?.unobserve(observedTurn);
    observedTurn=turn;
    if(turn)chatResizeObserver?.observe(turn);
  }
  measureChatSpace();
  if(force)followNewReply=true;
  if(force||(changed&&followNewReply))focusLatestQuestion();
  showLatestReplyButton();
}
function resetChatScroll(){
  followNewReply=false;
  if(observedTurn)chatResizeObserver?.unobserve(observedTurn);
  observedTurn=null;
  const button=document.getElementById("latest-reply");if(button)button.hidden=true;
}
function initChatScroll(){
  const pane=document.getElementById("chat-scroll");
  const stopFollowing=()=>{followNewReply=false;};
  pane.addEventListener("wheel",stopFollowing,{passive:true});
  pane.addEventListener("touchmove",stopFollowing,{passive:true});
  pane.addEventListener("keydown",event=>{if(["ArrowUp","ArrowDown","PageUp","PageDown","Home","End"," "].includes(event.key))stopFollowing();});
  pane.addEventListener("scroll",()=>{
    const question=latestChatTurn()?.querySelector(".question-bubble");
    if(question&&Math.abs(questionFocusTop(question,pane)-pane.getBoundingClientRect().top-12)>100)followNewReply=false;
    showLatestReplyButton();
  },{passive:true});
  document.getElementById("latest-reply").addEventListener("click",()=>{followNewReply=true;focusLatestQuestion();});
  chatResizeObserver=new ResizeObserver(()=>{measureChatSpace();showLatestReplyButton();});
  chatResizeObserver.observe(pane);
}

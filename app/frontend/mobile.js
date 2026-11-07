/* Mobile workspace drawer; the desktop sidebar stays available at wide widths. */
const mobileWidth=window.matchMedia("(max-width: 900px)");
let workspaceOpener=null;
function openWorkspace(){
  if(!mobileWidth.matches||document.body.classList.contains("workspace-open"))return;
  workspaceOpener=document.activeElement;
  const sidebar=document.getElementById("workspace-sidebar");
  sidebar.inert=false;
  sidebar.setAttribute("role","dialog");
  sidebar.setAttribute("aria-modal","true");
  document.body.classList.add("workspace-open");
  document.getElementById("mobile-menu").setAttribute("aria-expanded","true");
  document.getElementById("mobile-backdrop").hidden=false;
  document.querySelector("main").inert=true;
  document.querySelector(".mobile-topbar").inert=true;
  requestAnimationFrame(()=>{if(document.body.classList.contains("workspace-open"))document.getElementById("mobile-close").focus();});
}
function closeWorkspace(restoreFocus=true){
  const sidebar=document.getElementById("workspace-sidebar");
  const wasOpen=document.body.classList.contains("workspace-open");
  document.body.classList.remove("workspace-open");
  document.getElementById("mobile-menu").setAttribute("aria-expanded","false");
  document.getElementById("mobile-backdrop").hidden=true;
  document.querySelector("main").inert=false;
  document.querySelector(".mobile-topbar").inert=false;
  sidebar.inert=mobileWidth.matches;
  sidebar.removeAttribute("role");sidebar.removeAttribute("aria-modal");
  if(wasOpen&&restoreFocus)(workspaceOpener?.isConnected?workspaceOpener:document.getElementById("mobile-menu")).focus();
}
function initMobile(){
  const fitViewport=()=>document.documentElement.style.setProperty("--app-height",Math.round(window.visualViewport?.height||window.innerHeight)+"px");
  window.visualViewport?.addEventListener("resize",fitViewport);
  window.addEventListener("resize",fitViewport);fitViewport();
  document.getElementById("mobile-menu").addEventListener("click",openWorkspace);
  for(const id of ["mobile-close","mobile-backdrop","mobile-done"])document.getElementById(id).addEventListener("click",()=>closeWorkspace());
  function arrangeLearning(){
    closeWorkspace(false);
    const home=document.getElementById("learning-home"),dialog=document.getElementById("learning-dialog");
    if(dialog.open)dialog.close();
    const target=mobileWidth.matches?document.getElementById("learning-content"):home;
    for(const id of ["attention-lab","more-labs"])target.append(document.getElementById(id));
  }
  document.getElementById("mobile-new-chat").addEventListener("click",()=>{newConversation();document.getElementById("close-reader").click();});
  document.getElementById("mobile-learning").addEventListener("click",()=>{closeWorkspace();document.getElementById("learning-dialog").showModal();});
  mobileWidth.addEventListener("change",arrangeLearning);
  document.addEventListener("keydown",event=>{
    if(!document.body.classList.contains("workspace-open")||document.querySelector("dialog[open]"))return;
    if(event.key==="Escape"){event.preventDefault();closeWorkspace();}
    if(event.key==="Tab"){
      const items=[...document.getElementById("workspace-sidebar").querySelectorAll("button,a[href],input,select,textarea,[tabindex='0']")].filter(item=>!item.disabled&&item.getClientRects().length);
      const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
  });
  arrangeLearning();
}

/* garden2wikidocs: 사이드바 최상단 챕터 바로가기 주입 */
/*
 * 배포 위치: 위키독스 책 20676 → 책 수정 → "사용자 스타일/스크립트" 탭 → 사용자 스크립트(JS)
 *   URL: https://wikidocs.net/edit/book/20676  (필드 id=user_script, <script> 태그 없이 본문만)
 *
 * 왜 필요한가 (2026-07 코어 판본 기준으로 이유가 바뀌었다):
 *   [옛 이유 — 지금은 해당 없음] 위키독스 리더 사이드바 TOC는 서버가 HTML을 최대 1000노드까지만
 *   렌더한다(하드캡). 전량 발행 시절 이 책은 2244노드라 seq 순서로 채우다 1000에서 잘렸고,
 *   "4 노트"·"5 봇로그" 챕터 헤더가 raw HTML에 아예 emit되지 않아 사이드바에서 사라졌다.
 *   현재 코어 판본은 250노드라 하드캡에 걸리지 않는다. 챕터 6개가 모두 정상 렌더된다.
 *
 *   [현재 이유] 그래도 사이드바는 길다. "4 노트" 163개, "0 어쏠로그"·"5 봇로그"까지 펼치면
 *   챕터 간 이동에 계속 스크롤이 필요하다. 최상단 고정 바로가기가 그 왕복을 없앤다.
 *   발행면이 다시 1000노드를 넘기면 옛 이유가 그대로 부활하므로 스크립트는 유지한다.
 *
 * 유지보수: 아래 CH 배열은 TOC.md 챕터 목록·순서와 같아야 하고, page_id 는 mapping.json 의
 *   _chapters 와 일치해야 한다. 손으로 맞추는 값이라 `audit.py` 가 이 파일을 읽어 대조한다
 *   (어긋난 page_id = 오류, 회수했는데 아직 null = 경고). 챕터가 추가/재생성되면 CH 를 갱신하고
 *   위키독스 책 설정에 다시 붙여넣는다. user_script 는 GitHub 콘텐츠 동기화가 건드리지 않으므로
 *   한 번 저장하면 재동기화에도 유지된다.
 *   page_id 가 아직 없는 신규 표지는 null 로 두면 사이드바 DOM 에서 같은 제목의 링크를 찾아
 *   쓴다(발행 후에만 작동). recover 로 회수한 뒤 null 을 실제 page_id 로 바꾸면 폴백 없이 돈다.
 */
(function(){
  var CH=[[386464,'0 어쏠로그'],[380373,'1 저널'],[380477,'2 메타'],[381854,'3 참고문헌'],[381016,'4 노트'],[382535,'5 봇로그']];
  function chapterHref(c,sb){
    if(c[0]) return '/'+c[0];
    var links=sb.getElementsByTagName('a');
    for(var i=0;i<links.length;i++){
      if((links[i].textContent||'').replace(/\s+/g,' ').trim()===c[1]){
        return links[i].getAttribute('href');
      }
    }
    return null;
  }
  function inject(){
    var sb=document.querySelector('.col-sm-3.sidebar .toc.toc-checker');
    if(!sb) return false;
    if(document.getElementById('g2w-chapter-nav')) return true;
    var box=document.createElement('div');
    box.id='g2w-chapter-nav';
    box.style.cssText='padding:8px 0 10px;margin:0 0 6px;border-bottom:1px solid rgba(128,128,128,.25);';
    var h=document.createElement('div');
    h.textContent='📚 챕터';
    h.style.cssText='font-weight:600;font-size:12px;opacity:.55;padding:2px 14px 6px;';
    box.appendChild(h);
    CH.forEach(function(c){
      var href=chapterHref(c,sb);
      if(!href) return;
      var a=document.createElement('a');
      a.href=href;
      a.textContent=c[1];
      a.style.cssText='display:block;padding:4px 14px;font-size:14px;text-decoration:none;color:inherit;';
      if(c[0]===null) a.style.fontWeight='600';
      a.addEventListener('mouseover',function(){a.style.opacity='.65';});
      a.addEventListener('mouseout',function(){a.style.opacity='1';});
      box.appendChild(a);
    });
    sb.insertBefore(box, sb.firstChild);
    return true;
  }
  var n=0,iv=setInterval(function(){ if(inject()||++n>25) clearInterval(iv); },200);
})();

/* garden2wikidocs: 사이드바 TOC 서버 1000노드 하드캡 보정 — 전체 챕터 인덱스 주입 */
/*
 * 배포 위치: 위키독스 책 20676 → 책 수정 → "사용자 스타일/스크립트" 탭 → 사용자 스크립트(JS)
 *   URL: https://wikidocs.net/edit/book/20676  (필드 id=user_script, <script> 태그 없이 본문만)
 *
 * 왜 필요한가:
 *   위키독스 리더 사이드바 TOC는 서버가 HTML을 최대 1000노드까지만 렌더한다(하드캡).
 *   이 책은 2243노드(페이지 2238 + 챕터 5)라, seq 순서로 저널(103)+메타(538)+참고문헌
 *   자식 일부까지 채우고 1000에서 잘린다. 그 결과 "4 노트", "5 봇로그" 챕터 헤더가
 *   raw HTML에 아예 emit되지 않아 사이드바에서 사라진다(편집 트리는 별도 렌더러라 정상).
 *   접기(open_yn/toggleTocItem)는 localStorage 클라이언트 기능이라 서버 truncation을 못 되살린다.
 *   → 유일한 실질 해법: 클라이언트에서 전체 챕터 인덱스를 사이드바 최상단에 주입.
 *
 * 유지보수: 챕터 page_id는 mapping.json 의 _chapters 와 일치해야 한다. 챕터가 추가/재생성되면
 *   아래 CH 배열을 갱신하고 위키독스 책 설정에 다시 붙여넣는다. (user_script는 GitHub 콘텐츠
 *   동기화가 건드리지 않으므로 한 번 저장하면 재동기화에도 유지된다.)
 */
(function(){
  var CH=[[380373,'1 저널'],[380477,'2 메타'],[381854,'3 참고문헌'],[381016,'4 노트'],[382535,'5 봇로그']];
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
      var a=document.createElement('a');
      a.href='/'+c[0];
      a.textContent=c[1];
      a.style.cssText='display:block;padding:4px 14px;font-size:14px;text-decoration:none;color:inherit;';
      a.addEventListener('mouseover',function(){a.style.opacity='.65';});
      a.addEventListener('mouseout',function(){a.style.opacity='1';});
      box.appendChild(a);
    });
    sb.insertBefore(box, sb.firstChild);
    return true;
  }
  var n=0,iv=setInterval(function(){ if(inject()||++n>25) clearInterval(iv); },200);
})();
